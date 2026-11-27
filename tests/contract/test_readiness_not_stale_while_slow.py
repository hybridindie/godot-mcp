"""Contract: a slow in-flight command does not make a live editor 'stale' (#762 follow-up).

``Bridge.editor_status`` returns ``stale`` once any pending command is older
than 5s, even while heartbeats keep arriving, so a 6s bake turns every mutating
call into BRIDGE_DISCONNECTED ("the editor stopped responding").
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

# Commands the fake addon never answers: they stay in flight for the test.
_WITHHELD = {"cmd_bake_navigation_mesh", "cmd_get_scene_tree"}


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command in _WITHHELD:
        return None
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": True, "path": "res://m.tscn"})
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_create_node":
        return ResponseEnvelope.success(
            command.id,
            {"node_path": f"{command.params['parent_path']}/{command.params['name']}",
             "created": True},
        )
    return make_addon_responder(godot_version="4.7.2-stable")(command)


async def _heartbeat(conn: FakeAddonConnection, bridge: Bridge, clock: list[float]) -> None:
    await conn.push({"command": "cmd_editor_status", "params": {"status": "ready"}})
    for _ in range(100):
        if bridge._last_heartbeat == clock[0]:  # noqa: SLF001 — wait for the bridge to ingest it
            return
        await asyncio.sleep(0.01)
    raise AssertionError("heartbeat never reached the bridge")


async def test_slow_command_with_live_heartbeats_is_not_stale() -> None:
    clock = [1_000.0]
    conn = FakeAddonConnection(_responder)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn), clock=lambda: clock[0])
    await bridge.connect()
    await _heartbeat(conn, bridge, clock)
    slow = asyncio.create_task(bridge.send("cmd_bake_navigation_mesh", {"node_path": "Nav"}))
    await asyncio.sleep(0.01)
    clock[0] += 6.0  # the bake has run 6s; the editor still sends heartbeats
    await _heartbeat(conn, bridge, clock)
    try:
        assert bridge.editor_status != "stale"
    finally:
        slow.cancel()
        await bridge.close()
