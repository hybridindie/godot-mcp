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
        case "cmd_get_node_property":
            if cmd.params.get("node_path") == "Missing":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Missing'."
                )
            # A built-in property the script-var filter would have hidden.
            if cmd.params.get("property") == "position":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "node_path": cmd.params["node_path"],
                        "property": "position",
                        "value": {"x": 10.0, "y": 20.0},
                        "exists": True,
                    },
                )
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "property": cmd.params["property"],
                    "value": None,
                    "exists": False,
                },
            )
        case "cmd_get_node_groups":
            if cmd.params.get("node_path") == "Missing":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Missing'."
                )
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": cmd.params["node_path"], "groups": ["enemies", "spawnable"]},
            )
        case "cmd_list_scenes":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scenes": [
                        {
                            "path": "res://main.tscn",
                            "is_main": True,
                            "is_open": True,
                            "is_active": True,
                        },
                        {
                            "path": "res://enemy.tscn",
                            "is_main": False,
                            "is_open": False,
                            "is_active": False,
                        },
                    ],
                    "main_scene": "res://main.tscn",
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
        case "cmd_list_scenes":
            return ResponseEnvelope.success(cmd.id, {"scenes": [], "main_scene": None})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_get_project_info() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("godot_inspection_get_project_info", {})
    info = result.structured_content
    assert info["name"] == "demo"
    assert info["godot_version"] == "4.6.3"
    assert info["autoloads"] == {"Game": "res://game.gd"}
    assert info["input_actions"] == ["jump"]


async def test_get_active_scene() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("godot_inspection_get_active_scene", {})
    assert result.structured_content["is_open"] is True
    assert result.structured_content["name"] == "main.tscn"


async def test_list_scenes() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("godot_inspection_list_scenes", {})
    sc = result.structured_content
    assert sc["main_scene"] == "res://main.tscn"
    assert [s["path"] for s in sc["scenes"]] == ["res://main.tscn", "res://enemy.tscn"]
    main = sc["scenes"][0]
    assert main["is_main"] is True and main["is_open"] is True and main["is_active"] is True
    other = sc["scenes"][1]
    assert other["is_main"] is False and other["is_open"] is False


async def test_list_scenes_empty_project() -> None:
    # A net-new project (no scenes yet) returns an empty list, not an error — the agent
    # reads this as "create a scene", not "fail".
    async with Client(_build(FakeAddonConnection(responder=_empty))) as client:
        result = await client.call_tool("godot_inspection_list_scenes", {})
    assert result.structured_content["scenes"] == []
    assert result.structured_content["main_scene"] is None


async def test_get_scene_tree_passes_max_depth() -> None:
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_inspection_get_scene_tree", {"max_depth": 2})
    assert result.structured_content["tree"]["name"] == "Main"
    assert conn.last_command().params["max_depth"] == 2


async def test_scene_tree_carries_path_round_trips_into_tool() -> None:
    # #180: every node carries a scene-relative `path`; that exact string is accepted
    # verbatim by a path-taking tool (here get_node_properties) with no reconstruction.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        tree = await client.call_tool("godot_inspection_get_scene_tree", {})
        root = tree.structured_content["tree"]
        assert root["path"] == "."
        child_path = root["children"][0]["path"]
        assert child_path == "Player"
        # Feed the discovered path straight into a path-taking tool — no walking.
        info = await client.call_tool(
            "godot_inspection_get_node_properties", {"node_path": child_path}
        )
    assert info.structured_content["node_path"] == "Player"


async def test_get_scene_tree_lightweight_passes_flag() -> None:
    # #168: lightweight=True forwards to the addon so it can skip script serialization.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_inspection_get_scene_tree", {"lightweight": True})
    assert result.structured_content["tree"]["name"] == "Main"
    assert conn.last_command().params["lightweight"] is True


async def test_get_scene_tree_defaults_to_full() -> None:
    # Default stays full (lightweight=False) for back-compat.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        await client.call_tool("godot_inspection_get_scene_tree", {})
    assert conn.last_command().params["lightweight"] is False


async def test_get_selected_node() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool("godot_inspection_get_selected_node", {})
    selected = result.structured_content["selected"]
    assert selected["node_path"] == "Player"
    assert selected["properties"]["speed"] == 200.0


async def test_get_node_properties_success() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_properties", {"node_path": "Player/Sprite2D"}
        )
    assert result.structured_content["node_path"] == "Player/Sprite2D"
    assert result.structured_content["type"] == "Sprite2D"


async def test_get_node_properties_missing_is_structured_error() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_properties", {"node_path": "Missing"}, raise_on_error=False
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_get_node_property_reads_builtin() -> None:
    # #215: reads a built-in property (position) the script-var filter would hide.
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_property", {"node_path": "Player", "property": "position"}
        )
    data = result.structured_content
    assert data["node_path"] == "Player"
    assert data["property"] == "position"
    assert data["exists"] is True
    assert data["value"] == {"x": 10.0, "y": 20.0}
    assert conn.last_command().params["property"] == "position"


async def test_get_node_property_absent_reports_exists_false() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_property", {"node_path": "Player", "property": "nope"}
        )
    data = result.structured_content
    assert data["exists"] is False
    assert data["value"] is None


async def test_get_node_property_missing_node_is_structured_error() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_property",
            {"node_path": "Missing", "property": "position"},
            raise_on_error=False,
        )
    assert result.is_error


async def test_get_node_groups_success() -> None:
    # #216: returns the node's group memberships (so add/remove_from_group is invertible).
    conn = FakeAddonConnection(responder=_populated)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_inspection_get_node_groups", {"node_path": "Player"})
    data = result.structured_content
    assert data["node_path"] == "Player"
    assert data["groups"] == ["enemies", "spawnable"]


async def test_get_node_groups_missing_is_structured_error() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        result = await client.call_tool(
            "godot_inspection_get_node_groups", {"node_path": "Missing"}, raise_on_error=False
        )
    assert result.is_error


async def test_inspection_tools_are_read_only() -> None:
    async with Client(_build(FakeAddonConnection(responder=_populated))) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in (
        "godot_inspection_get_project_info",
        "godot_inspection_get_active_scene",
        "godot_inspection_get_scene_tree",
        "godot_inspection_get_selected_node",
        "godot_inspection_get_node_properties",
        "godot_inspection_get_node_property",
        "godot_inspection_get_node_groups",
    ):
        assert by_name[name].meta is not None
        assert by_name[name].meta.get("safety_class") == "read_only"


async def test_inspection_handles_no_open_scene() -> None:
    async with Client(_build(FakeAddonConnection(responder=_empty))) as client:
        scene = await client.call_tool("godot_inspection_get_active_scene", {})
        tree = await client.call_tool("godot_inspection_get_scene_tree", {})
        selected = await client.call_tool("godot_inspection_get_selected_node", {})
    assert scene.structured_content["is_open"] is False
    assert tree.structured_content["tree"] is None
    assert selected.structured_content["selected"] is None
