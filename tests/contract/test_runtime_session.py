"""Contract tests for the runtime session bridge (issue #66)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_TREE = {
    "name": "root",
    "type": "Window",
    "path": "/root",
    "children": [{"name": "Main", "type": "Node2D", "path": "/root/Main", "children": []}],
}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_play_scene":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "scene": p.get("scene_path") or "<main>"}
            )
        case "cmd_stop_scene":
            return ResponseEnvelope.success(cmd.id, {"playing": False})
        case "cmd_is_playing":
            return ResponseEnvelope.success(cmd.id, {"playing": True, "scene": "res://main.tscn"})
        case "cmd_get_game_scene_tree":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "connected": True, "tree": _TREE}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_in_runtime_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_runtime_play_scene" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    assert {
        "godot_runtime_play_scene",
        "godot_runtime_stop_scene",
        "godot_runtime_is_playing",
        "godot_runtime_get_game_scene_tree",
    } <= set(tools)
    assert tools["godot_runtime_play_scene"].meta["safety_class"] == "runtime"
    assert tools["godot_runtime_stop_scene"].meta["safety_class"] == "runtime"
    assert tools["godot_runtime_is_playing"].meta["safety_class"] == "read_only"
    assert tools["godot_runtime_get_game_scene_tree"].meta["safety_class"] == "read_only"


async def test_play_stop_and_is_playing() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        played = await client.call_tool(
            "godot_runtime_play_scene", {"scene_path": "res://main.tscn"}
        )
        playing = await client.call_tool("godot_runtime_is_playing", {})
        stopped = await client.call_tool("godot_runtime_stop_scene", {})
    assert played.structured_content["playing"] is True
    assert played.structured_content["scene"] == "res://main.tscn"
    assert playing.structured_content["playing"] is True
    assert stopped.structured_content["playing"] is False


async def test_get_game_scene_tree_returns_live_tree() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool("godot_runtime_get_game_scene_tree", {})
    sc = result.structured_content
    assert sc["connected"] is True
    assert sc["tree"]["type"] == "Window"
    assert sc["tree"]["children"][0]["name"] == "Main"


async def test_get_game_scene_tree_not_connected() -> None:
    # The addon reports playing-but-probe-not-connected as a soft result, not an error.
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_game_scene_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {"playing": True, "connected": False, "tree": None, "hint": "add the probe"},
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool("godot_runtime_get_game_scene_tree", {})
    assert result.structured_content["connected"] is False
    assert result.structured_content["tree"] is None
    assert "probe" in result.structured_content["hint"]
