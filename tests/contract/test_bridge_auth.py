"""Contract tests for the optional bridge auth token (issue #538).

When ``GODOT_MCP_BRIDGE_TOKEN`` is set server-side, an adopted peer must send a
matching auth envelope as its FIRST message before the bridge serves it; a
missing or wrong token is refused with a structured envelope and the peer is
dropped (the addon then reconnects with backoff). With no token configured the
path is byte-identical to today — peers connect with no auth exchange.
"""

from __future__ import annotations

import json
import logging

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _auth_envelope(token: str) -> str:
    return json.dumps({"id": "auth", "command": "cmd_auth", "params": {"token": token}})


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


async def test_auth_resets_with_the_peer() -> None:
    """A replaced peer must re-authenticate: the previous peer's auth state
    never leaks to the next connection."""
    first = FakeAddonConnection()
    first._incoming.put_nowait(_auth_envelope("secret-token"))
    bridge = Bridge(BridgeConfig(auth_token="secret-token"), connector=connector_for(first))
    await bridge.connect()
    assert bridge.connected is True

    second = FakeAddonConnection()  # no auth — must be refused
    bridge._connector = connector_for(second)
    await bridge.connect()
    try:
        assert bridge.connected is False
        assert second.closed is True
    finally:
        await bridge.close()


async def test_bridge_config_reads_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """GODOT_MCP_BRIDGE_TOKEN flows into BridgeConfig.from_env (mirrors the URL)."""
    monkeypatch.setenv("GODOT_MCP_BRIDGE_TOKEN", "env-token")
    config = BridgeConfig.from_env()
    assert config.auth_token == "env-token"
    monkeypatch.delenv("GODOT_MCP_BRIDGE_TOKEN")
    assert BridgeConfig.from_env().auth_token is None