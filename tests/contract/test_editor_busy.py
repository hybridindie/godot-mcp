"""Contract: readiness heartbeat gates mutating calls (#762)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": True, "path": "res://m.tscn"})
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_create_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": f"{command.params['parent_path']}/{command.params['name']}",
                "created": True,
            },
        )
    return make_addon_responder(godot_version="4.7.2-stable")(command)


def _server(clock: list[float]) -> tuple[FastMCP, FakeAddonConnection, Bridge]:
    config = ServerConfig()
    conn = FakeAddonConnection(_responder)
    bridge = Bridge(
        config.bridge,
        connector=connector_for(conn),
        clock=lambda: clock[0],
    )
    return create_server(config, bridge=bridge), conn, bridge


async def _push(conn: FakeAddonConnection, bridge: Bridge, status: str) -> None:
    await conn.push({"command": "cmd_editor_status", "params": {"status": status}})
    for _ in range(100):
        if bridge.editor_status == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"status {status!r} never reached the bridge ({bridge.editor_status!r})")


async def test_importing_editor_fails_fast_with_editor_busy() -> None:
    server, conn, bridge = _server([1_000.0])
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await _push(conn, bridge, "importing")
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["error"] == "EDITOR_BUSY"
    assert payload["next_call"]["tool"] == "godot_health_check"
    assert "cmd_create_node" not in [json.loads(s)["command"] for s in conn.sent]


async def test_read_only_tools_are_not_blocked() -> None:
    server, conn, bridge = _server([1_000.0])
    async with Client(server, mode="legacy") as client:
        await _push(conn, bridge, "importing")
        result = await client.call_tool("godot_health_check", {})
    assert result.structured_content["editor_status"] == "importing"


async def test_stale_heartbeat_is_bridge_disconnected() -> None:
    clock = [1_000.0]
    server, conn, bridge = _server(clock)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await _push(conn, bridge, "ready")
        clock[0] += 6.0
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "BRIDGE_DISCONNECTED"
    assert "stopped responding" in result.structured_content["hint"]


async def test_server_info_exposes_editor_status() -> None:
    server, conn, bridge = _server([1_000.0])
    async with Client(server, mode="legacy") as client:
        await _push(conn, bridge, "modal")
        info = await client.call_tool("godot_get_server_info", {})
    assert info.structured_content["bridge"]["editor_status"] == "modal"
