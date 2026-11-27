"""Contract: a command the editor is executing synchronously reads as busy, not stale (#905).

The addon runs each command on the editor main thread and sends its heartbeat
from the same ``_process``, so no heartbeat can arrive while a command runs.
``Bridge.editor_status`` must treat "heartbeats stopped + a command pending
within its own timeout" as ``busy``; ``stale`` is reserved for silence with
nothing pending, or a pending command that outlived its own timeout.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio

_WITHHELD = {"cmd_bake_navigation_mesh"}
_TIMEOUT = 10.0


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command in _WITHHELD:
        return None
    return make_addon_responder(godot_version="4.7.2-stable")(command)


async def _heartbeat(conn: FakeAddonConnection, bridge: Bridge, clock: list[float]) -> None:
    await conn.push({"command": "cmd_editor_status", "params": {"status": "ready"}})
    for _ in range(100):
        if bridge._last_heartbeat == clock[0]:  # noqa: SLF001 — wait for the bridge to ingest it
            return
        await asyncio.sleep(0.01)
    raise AssertionError("heartbeat never reached the bridge")


async def _bridge(clock: list[float]) -> tuple[Bridge, FakeAddonConnection]:
    conn = FakeAddonConnection(_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn), clock=lambda: clock[0])
    await bridge.connect()
    await _heartbeat(conn, bridge, clock)
    return bridge, conn


async def test_synchronous_command_without_heartbeats_is_busy_until_its_timeout() -> None:
    clock = [1_000.0]
    bridge, _ = await _bridge(clock)
    # The injected clock drives readiness; the real sleep of _TIMEOUT never
    # elapses during the test, so the command stays pending throughout.
    slow = asyncio.create_task(
        bridge.send("cmd_bake_navigation_mesh", {"node_path": "Nav"}, timeout=_TIMEOUT)
    )
    await asyncio.sleep(0.01)
    try:
        clock[0] += 6.0  # executing synchronously: no heartbeat for 6s
        assert bridge.editor_status == "busy"
        clock[0] += _TIMEOUT  # now past the command's own deadline
        assert bridge.editor_status == "stale"
    finally:
        slow.cancel()
        await bridge.close()


async def test_no_heartbeat_with_nothing_pending_is_stale() -> None:
    clock = [1_000.0]
    bridge, _ = await _bridge(clock)
    try:
        clock[0] += 6.0
        assert bridge.editor_status == "stale"
    finally:
        await bridge.close()


async def test_cancelled_send_leaves_nothing_pending() -> None:
    """A caller cancelled mid-request (MCP clients cancel in-flight calls) must
    not leave its entry behind: under the #905 rule a leaked entry would decide
    editor_status (busy, then stale) long after the call is gone."""
    clock = [1_000.0]
    bridge, _ = await _bridge(clock)
    slow = asyncio.create_task(
        bridge.send("cmd_bake_navigation_mesh", {"node_path": "Nav"}, timeout=_TIMEOUT)
    )
    await asyncio.sleep(0.01)
    try:
        assert bridge._pending_started  # noqa: SLF001 — the request is in flight
        slow.cancel()
        with pytest.raises(asyncio.CancelledError):
            await slow
        assert not bridge._pending  # noqa: SLF001
        assert not bridge._pending_commands  # noqa: SLF001
        assert not bridge._pending_started  # noqa: SLF001
        assert not bridge._pending_deadline  # noqa: SLF001
        clock[0] += 6.0
        assert bridge.editor_status == "stale"  # nothing pending, no heartbeat
    finally:
        await bridge.close()
