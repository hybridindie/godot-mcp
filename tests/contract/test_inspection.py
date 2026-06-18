"""Contract tests for the read-only inspection tools (issue #5).

Drive the real FastMCP server over the in-memory client, backed by a fake addon
peer with canned responses: verify each tool routes to the right command, maps
the JSON-safe response to its typed model, handles empty/no-scene state, and
surfaces structured errors.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _populated(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_get_project_info":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "name": "demo",
                    "godot_version": "4.6.3",
                    "main_scene": "res://main.tscn",
                    "autoloads": {"Game": "res://game.gd"},
                    "input_actions": ["jump"],
                },
            )
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(
                cmd.id, {"is_open": True, "path": "res://main.tscn", "name": "main.tscn"}
            )
        case "cmd_get_scene_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "tree": {
                        "name": "Main",
                        "type": "Node2D",
                        "path": ".",
                        "script": None,
                        "children": [
                            {
                                "name": "Player",
                                "type": "CharacterBody2D",
                                "path": "Player",
                                "script": None,
                                "children": [],
                            }
                        ],
                    }
                },
            )
        case "cmd_get_selected_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "selected": {
                        "node_path": "Player",
                        "type": "CharacterBody2D",
                        "script": "res://player.gd",
                        "properties": {"speed": 200.0},
                        "children": ["Sprite2D"],
                    }
                },
            )
        case "cmd_get_node_properties":
            if cmd.params.get("node_path") == "Missing":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Missing'."
                )
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "type": "Sprite2D",
                    "script": None,
                    "properties": {},
                    "children": [],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _empty(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": False, "path": None, "name": None})
        case "cmd_get_scene_tree":
            return ResponseEnvelope.success(cmd.id, {"tree": None})
        case "cmd_get_selected_node":
            return ResponseEnvelope.success(cmd.id, {"selected": None})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_get_project_info() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("get_project_info", {})
    info = result.structured_content
    assert info["name"] == "demo"
    assert info["godot_version"] == "4.6.3"
    assert info["autoloads"] == {"Game": "res://game.gd"}
    assert info["input_actions"] == ["jump"]


async def test_get_active_scene() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("get_active_scene", {})
    assert result.structured_content["is_open"] is True
    assert result.structured_content["name"] == "main.tscn"


async def test_get_scene_tree_passes_max_depth() -> None:
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("get_scene_tree", {"max_depth": 2})
    assert result.structured_content["tree"]["name"] == "Main"
    assert conn.last_command().params["max_depth"] == 2


async def test_scene_tree_carries_path_round_trips_into_tool() -> None:
    # #180: every node carries a scene-relative `path`; that exact string is accepted
    # verbatim by a path-taking tool (here get_node_properties) with no reconstruction.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        tree = await client.call_tool("get_scene_tree", {})
        root = tree.structured_content["tree"]
        assert root["path"] == "."
        child_path = root["children"][0]["path"]
        assert child_path == "Player"
        # Feed the discovered path straight into a path-taking tool — no walking.
        info = await client.call_tool("get_node_properties", {"node_path": child_path})
    assert info.structured_content["node_path"] == "Player"


async def test_get_scene_tree_lightweight_passes_flag() -> None:
    # #168: lightweight=True forwards to the addon so it can skip script serialization.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("get_scene_tree", {"lightweight": True})
    assert result.structured_content["tree"]["name"] == "Main"
    assert conn.last_command().params["lightweight"] is True


async def test_get_scene_tree_defaults_to_full() -> None:
    # Default stays full (lightweight=False) for back-compat.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        await client.call_tool("get_scene_tree", {})
    assert conn.last_command().params["lightweight"] is False


async def test_get_selected_node() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("get_selected_node", {})
    selected = result.structured_content["selected"]
    assert selected["node_path"] == "Player"
    assert selected["properties"]["speed"] == 200.0


async def test_get_node_properties_success() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("get_node_properties", {"node_path": "Player/Sprite2D"})
    assert result.structured_content["node_path"] == "Player/Sprite2D"
    assert result.structured_content["type"] == "Sprite2D"


async def test_get_node_properties_missing_is_structured_error() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "get_node_properties", {"node_path": "Missing"}, raise_on_error=False
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_inspection_tools_are_read_only() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in (
        "get_project_info",
        "get_active_scene",
        "get_scene_tree",
        "get_selected_node",
        "get_node_properties",
    ):
        assert by_name[name].meta is not None
        assert by_name[name].meta.get("safety_class") == "read_only"


async def test_inspection_handles_no_open_scene() -> None:
    async with Client(_build(FakeAddonConnection(responder=_empty))) as client:
        scene = await client.call_tool("get_active_scene", {})
        tree = await client.call_tool("get_scene_tree", {})
        selected = await client.call_tool("get_selected_node", {})
    assert scene.structured_content["is_open"] is False
    assert tree.structured_content["tree"] is None
    assert selected.structured_content["selected"] is None
