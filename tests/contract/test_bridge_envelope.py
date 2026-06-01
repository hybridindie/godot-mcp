"""Contract tests for the WebSocket bridge envelope (issue #3).

The bridge is the core seam, so these pin the wire contract — command shape,
``id`` correlation, structured error pass-through, timeout, and the
disconnected case — against a fake addon peer (no sockets, no editor).
See .claude/rules/testing.md and docs/architecture.md.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from tests.fakes import (
    FakeAddonConnection,
    connector_for,
    immediate_sleep,
    ping_responder,
)

pytestmark = pytest.mark.asyncio


async def _connected_bridge(conn: FakeAddonConnection, **kwargs: object) -> Bridge:
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn), **kwargs)  # type: ignore[arg-type]
    await bridge.connect()
    return bridge


async def test_ping_returns_pong() -> None:
    conn = FakeAddonConnection()
    bridge = await _connected_bridge(conn)
    assert await bridge.ping() is True
    await bridge.close()


async def test_send_emits_command_envelope_on_the_wire() -> None:
    conn = FakeAddonConnection()
    bridge = await _connected_bridge(conn)

    await bridge.send("ping", {"a": 1})

    wire = json.loads(conn.sent[-1])
    assert set(wire) == {"id", "command", "params"}
    assert wire["command"] == "ping"
    assert wire["params"] == {"a": 1}
    await bridge.close()


async def test_response_is_correlated_by_id() -> None:
    # Each concurrent request must resolve to the response carrying its own id.
    def echo_id(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"command": cmd.command})

    conn = FakeAddonConnection(responder=echo_id)
    bridge = await _connected_bridge(conn)

    results = await asyncio.gather(
        bridge.send("alpha"),
        bridge.send("beta"),
        bridge.send("gamma"),
    )
    assert [r.result and r.result["command"] for r in results] == ["alpha", "beta", "gamma"]
    await bridge.close()


async def test_structured_error_passes_through() -> None:
    def fail(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(
            cmd.id, "PRECONDITION_FAILED", "Open a scene first.", required="active_scene"
        )

    conn = FakeAddonConnection(responder=fail)
    bridge = await _connected_bridge(conn)

    resp = await bridge.send("create_node")
    assert resp.ok is False
    assert resp.error == "PRECONDITION_FAILED"
    assert resp.hint == "Open a scene first."
    assert resp.required == "active_scene"
    await bridge.close()


async def test_unknown_command_yields_validation_error() -> None:
    conn = FakeAddonConnection(responder=ping_responder)
    bridge = await _connected_bridge(conn)
    resp = await bridge.send("does_not_exist")
    assert resp.ok is False
    assert resp.error == "VALIDATION_ERROR"
    await bridge.close()


async def test_timeout_returns_timeout_envelope() -> None:
    # Silent peer + immediate (fake) sleep ⇒ the timeout branch fires deterministically.
    silent = FakeAddonConnection(responder=lambda _cmd: None)
    bridge = await _connected_bridge(silent, sleep=immediate_sleep)

    resp = await bridge.send("ping", timeout=5.0)
    assert resp.ok is False
    assert resp.error == "TIMEOUT"
    assert resp.hint  # actionable, non-empty
    await bridge.close()


async def test_send_without_connection_is_structured_error() -> None:
    bridge = Bridge(BridgeConfig())  # never connected
    resp = await bridge.send("ping")
    assert resp.ok is False
    assert resp.error == "BRIDGE_DISCONNECTED"


async def test_send_failure_mid_flight_is_structured_not_raised() -> None:
    # A transport that drops on send must yield a structured envelope, never raise.
    conn = FakeAddonConnection(send_error=ConnectionError("dropped"))
    bridge = await _connected_bridge(conn)

    resp = await bridge.send("ping")
    assert resp.ok is False
    assert resp.error == "BRIDGE_DISCONNECTED"
    assert bridge.connected is False  # marked disconnected for the next caller
    await bridge.close()
