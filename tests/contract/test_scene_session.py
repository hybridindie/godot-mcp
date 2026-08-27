"""Contract tests for the scene session tools (issue #79).

Drive the real FastMCP server over the in-memory client with a fake addon peer:
verify safety classes, that dry_run previews without sending a command, that
reload_scene needs confirm (destructive), and that results map to typed models.
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


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://world.tscn"})
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        case "cmd_open_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scene_path": p["scene_path"],
                    "opened": True,
                    "already_open": False,
                },
            )
        case "cmd_reload_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scene_path": p["scene_path"],
                    "reloaded": True,
                },
            )
        case "cmd_save_all_scenes":
            return ResponseEnvelope.success(cmd.id, {"saved": True, "count": 3})
        case "cmd_list_open_scenes":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scenes": [
                        {"path": "res://a.tscn"},
                        {"path": "res://b.tscn"},
                    ]
                },
            )
        case "cmd_select_nodes":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scene_path": p.get("scene_path", "res://world.tscn"),
                    "selected": p["node_paths"],
                    "count": len(p["node_paths"]),
                },
            )
        case "cmd_close_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scene_path": p.get("scene_path", "res://world.tscn"),
                    "closed": True,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_scene_session_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_scene_edit_open_scene"].meta["safety_class"] == "mutating"
    assert tools["godot_scene_edit_reload_scene"].meta["safety_class"] == "destructive"
    assert tools["godot_scene_edit_save_all_scenes"].meta["safety_class"] == "mutating"
    assert tools["godot_scene_edit_select_nodes"].meta["safety_class"] == "mutating"


async def test_open_scene_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_open_scene", {"scene_path": "res://level.tscn"}
        )
    assert result.structured_content["opened"] is True
    assert result.structured_content["scene_path"] == "res://level.tscn"
    assert "cmd_open_scene" in _commands(conn)


async def test_open_scene_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_open_scene", {"scene_path": "res://level.tscn", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["opened"] is False
    assert "cmd_open_scene" not in _commands(conn)


async def test_reload_scene_requires_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_reload_scene",
            {"scene_path": "res://level.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_reload_scene" not in _commands(conn)


async def test_reload_scene_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_reload_scene", {"scene_path": "res://level.tscn", "confirm": True}
        )
    assert result.structured_content["reloaded"] is True
    assert "cmd_reload_scene" in _commands(conn)


async def test_reload_scene_dry_run_needs_no_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_reload_scene", {"scene_path": "res://level.tscn", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["reloaded"] is False
    assert "cmd_reload_scene" not in _commands(conn)


async def test_save_all_scenes_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool("godot_scene_edit_save_all_scenes")
    assert result.structured_content["saved"] is True
    assert result.structured_content["count"] == 3
    assert "cmd_save_all_scenes" in _commands(conn)


async def test_save_all_scenes_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool("godot_scene_edit_save_all_scenes", {"dry_run": True})
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["saved"] is False
    assert "cmd_save_all_scenes" not in _commands(conn)


async def test_list_open_scenes_is_read_only() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
        result = await client.call_tool("godot_scene_edit_list_open_scenes")
    assert tools["godot_scene_edit_list_open_scenes"].meta["safety_class"] == "read_only"
    scenes = result.structured_content["scenes"]
    assert len(scenes) == 2
    assert scenes[0]["path"] == "res://a.tscn"
    assert "cmd_list_open_scenes" in _commands(conn)


async def test_select_nodes_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_select_nodes",
            {"node_paths": ["Player", "Enemy"]},
        )
    assert result.structured_content["count"] == 2
    assert result.structured_content["selected"] == ["Player", "Enemy"]
    assert "cmd_select_nodes" in _commands(conn)


async def test_select_nodes_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_select_nodes",
            {"node_paths": ["Player"], "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["count"] == 1
    assert "cmd_select_nodes" not in _commands(conn)


# --- close_scene (issue #355) ----------------------------------------------


async def test_close_scene_safety_class_is_destructive() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
    assert "godot_scene_edit_close_scene" in tools, "close_scene tool not registered"
    assert tools["godot_scene_edit_close_scene"].meta["safety_class"] == "destructive"


async def test_close_scene_requires_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_close_scene",
            {"scene_path": "res://level.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_close_scene" not in _commands(conn)


async def test_close_scene_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_close_scene",
            {"scene_path": "res://level.tscn", "confirm": True},
        )
    assert result.structured_content["closed"] is True
    assert result.structured_content["scene_path"] == "res://level.tscn"
    assert "cmd_close_scene" in _commands(conn)


async def test_close_scene_dry_run_needs_no_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_close_scene",
            {"scene_path": "res://level.tscn", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["closed"] is False
    assert "cmd_close_scene" not in _commands(conn)


async def test_close_scene_requires_active_scene() -> None:
    # When no scene is open the addon reports active_scene missing; the server
    # surfaces it as a structured precondition failure rather than a traceback.
    def no_scene_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_active_scene":
            return ResponseEnvelope.failure(
                cmd.id, "PRECONDITION_FAILED", "No scene is open.", "active_scene"
            )
        return _responder(cmd)

    conn = FakeAddonConnection(responder=no_scene_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_close_scene",
            {"confirm": True},
            raise_on_error=False,
        )
    assert result.is_error
    assert "active_scene" in str(result.content)
    assert "cmd_close_scene" not in _commands(conn)
