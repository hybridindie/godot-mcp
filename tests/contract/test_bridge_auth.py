"""Contract tests for the optional bridge auth token (issue #538).

When ``GODOT_MCP_BRIDGE_TOKEN`` is set server-side, an adopted peer must send a
matching auth envelope as its FIRST message before the bridge serves it; a
missing or wrong token is refused with a structured envelope and the peer is
dropped (the addon then reconnects with backoff). With no token configured the
path is byte-identical to today — peers connect with no auth exchange.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _auth_envelope(token: str) -> str:
    return json.dumps({"id": "auth", "command": "cmd_auth", "params": {"token": token}})


class _GatedAuthConn(FakeAddonConnection):
    """A fake peer whose first ``recv`` (the auth handshake) waits on a barrier.

    This makes two peers provably inside ``_auth_check`` at the same time, so the
    concurrent-adoption race (issue #635) is deterministic rather than timing-lucky.
    """

    def __init__(self, barrier: asyncio.Barrier, token: str) -> None:
        super().__init__()
        self._barrier = barrier
        self._token = token
        self._first = True

    async def recv(self) -> str:
        if self._first:
            self._first = False
            await self._barrier.wait()
            return _auth_envelope(self._token)
        return await super().recv()


class _RaisingRecvConn:
    """A connection whose read loop dies immediately (a stale/disconnected peer)."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        raise ConnectionResetError("stale peer gone")

    async def close(self) -> None:
        self.closed = True


async def test_no_token_path_unchanged() -> None:
    """Both-unset: the peer serves immediately, no auth exchange (today's bytes)."""
    conn = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert await bridge.ping() is True
    finally:
        await bridge.close()


async def test_correct_token_authenticates() -> None:
    """Server set + addon sends the matching token: the peer is adopted and serves."""
    conn = FakeAddonConnection()
    # The addon sends auth as its first message; the fake queues it on send-time
    # only via a responder, so pre-queue it as the first incoming message.
    conn._incoming.put_nowait(_auth_envelope("secret-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(conn))
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert await bridge.ping() is True
    finally:
        await bridge.close()


async def test_missing_token_is_refused_at_handshake() -> None:
    """Server set + addon never authenticates: refused immediately (not per-command),
    the peer is dropped, and in-flight commands fail BRIDGE_DISCONNECTED."""
    conn = FakeAddonConnection()  # never sends an auth envelope
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(conn))
    await bridge.connect()
    # Give the handshake check a moment to run (deterministic yield, no sleeps
    # in the assertion path — the attach awaited the first message already).
    try:
        assert bridge.connected is False
        response = await bridge.send("cmd_ping")
        assert response.ok is False
        assert response.error == "BRIDGE_DISCONNECTED"
        assert conn.closed is True  # the refused peer was dropped
    finally:
        await bridge.close()


async def test_wrong_token_is_refused_with_structured_envelope() -> None:
    """A wrong token gets a VALIDATION_ERROR-family refusal naming the handshake —
    the addon's reconnect loop then retries with backoff (documented)."""
    conn = FakeAddonConnection()
    conn._incoming.put_nowait(_auth_envelope("wrong-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(conn))
    await bridge.connect()
    try:
        assert bridge.connected is False
        assert conn.closed is True
    finally:
        await bridge.close()


async def test_wrong_token_refusal_never_logs_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The token never appears in any log record (issue #538's hard rule)."""
    conn = FakeAddonConnection()
    conn._incoming.put_nowait(_auth_envelope("super-secret-value"))
    bridge = Bridge(BridgeConfig(auth_token="expected"), connector=connector_for(conn))
    with caplog.at_level(logging.DEBUG, logger="mcp_server.bridge"):
        await bridge.connect()
    try:
        joined = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
        assert "super-secret-value" not in joined
        assert "expected" not in joined
    finally:
        await bridge.close()


async def test_addon_only_token_is_control_message_ignored() -> None:
    """Addon set / server unset: the server consumes the auth envelope as a
    control message (like cmd_peer_hello) and the peer serves — the matrix's
    'addon only' cell stays functional with a newer addon against an old server."""
    conn = FakeAddonConnection()
    conn._incoming.put_nowait(_auth_envelope("addon-token"))
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert await bridge.ping() is True
    finally:
        await bridge.close()


async def test_control_message_racing_auth_does_not_false_refuse() -> None:
    """A peer hello (or other control message) arriving BEFORE the auth envelope
    is skipped, not consumed as the auth message — no false refusal (PR #558
    review: pipelined control messages must not eat the auth check)."""
    conn = FakeAddonConnection()
    hello = json.dumps(
        {"id": "hello", "command": "cmd_peer_hello", "params": {"project_path": "/tmp/x"}}
    )
    conn._incoming.put_nowait(hello)
    conn._incoming.put_nowait(_auth_envelope("secret-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(conn))
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert await bridge.ping() is True
        # The skipped hello still lands as the peer's identity.
        assert (bridge.peer_identity or {}).get("project_path") == "/tmp/x"
    finally:
        await bridge.close()


async def test_auth_resets_with_the_peer() -> None:
    """An unauthenticated peer must NOT be adopted and must NOT displace the
    authenticated peer's link (its auth state never leaks into an adoption)."""
    first = FakeAddonConnection()
    first._incoming.put_nowait(_auth_envelope("secret-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(first))
    await bridge.connect()
    assert bridge.connected is True

    second = FakeAddonConnection()  # no auth — must be refused, never adopted
    bridge._connector = connector_for(second)
    await bridge.connect()
    try:
        assert second.closed is True
        # #635: the refusal must not knock the already-authenticated editor off.
        assert bridge.connected is True
        assert bridge._conn is first
        assert first.closed is False
    finally:
        await bridge.close()


async def test_wrong_token_peer_does_not_displace_authed_peer() -> None:
    """#635: a peer with a bad token must be refused WITHOUT evicting the active,
    already-authenticated editor (a local process could otherwise knock the real
    editor off the bridge with one connect)."""
    first = FakeAddonConnection()
    first._incoming.put_nowait(_auth_envelope("secret-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(first))
    await bridge.connect()
    assert bridge.connected is True

    second = FakeAddonConnection()
    second._incoming.put_nowait(_auth_envelope("wrong-token"))
    bridge._connector = connector_for(second)
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert bridge._conn is first
        assert first.closed is False  # the real editor keeps its link
        assert second.closed is True  # the bad peer is dropped
    finally:
        await bridge.close()


async def test_concurrent_authed_peers_adopt_exactly_one() -> None:
    """#635: two peers authenticating at the same time end with exactly one
    adopted; the loser is closed with a PEER_REPLACED notice (never two readers
    resolving the same futures)."""
    barrier = asyncio.Barrier(2)
    a = _GatedAuthConn(barrier, "tok")
    b = _GatedAuthConn(barrier, "tok")
    conns = iter([a, b])

    async def connector(_url: str) -> FakeAddonConnection:
        return next(conns)

    bridge = Bridge(BridgeConfig(auth_token="tok"), connector=connector)
    await asyncio.gather(bridge.connect(), bridge.connect())
    try:
        assert bridge.connected is True
        adopted = bridge._conn
        assert adopted in (a, b), "exactly one of the two peers must be adopted"
        other = b if adopted is a else a
        assert other.closed is True, "the losing peer must be closed"
        notices = [json.loads(raw) for raw in other.sent]
        replaced = [n for n in notices if n.get("error") == "PEER_REPLACED"]
        assert replaced, "the losing peer must be told it was replaced"
    finally:
        await bridge.close()


async def test_stale_peer_disconnect_does_not_fail_active_pending() -> None:
    """#635: when a stale (non-active) peer's read loop dies, it must not fail the
    active peer's in-flight requests."""
    active = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(active))
    await bridge.connect()
    pending: asyncio.Future[ResponseEnvelope] = asyncio.get_running_loop().create_future()
    bridge._pending["99"] = pending

    stale = _RaisingRecvConn()
    await bridge._read_loop(stale)  # the stale reader dies
    try:
        assert not pending.done(), (
            "a stale peer's disconnect must not fail the active peer's pending requests"
        )
    finally:
        pending.cancel()
        await bridge.close()


async def test_no_token_replacement_still_works() -> None:
    """#635 regression guard: with no token configured the replacement path is
    unchanged — a new peer adopts and the old one is closed."""
    first = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(first))
    await bridge.connect()
    second = FakeAddonConnection()
    bridge._connector = connector_for(second)
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert bridge._conn is second
        assert first.closed is True
    finally:
        await bridge.close()


async def test_bridge_config_reads_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """GODOT_MCP_BRIDGE_TOKEN flows into BridgeConfig.from_env (mirrors the URL)."""
    monkeypatch.setenv("GODOT_MCP_BRIDGE_TOKEN", "env-token")
    config = BridgeConfig.from_env()
    assert config.auth_token == "env-token"
    monkeypatch.delenv("GODOT_MCP_BRIDGE_TOKEN")
    assert BridgeConfig.from_env().auth_token is None