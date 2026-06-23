"""Contract tests for the scene mutation tools (issue #6).

Drive the real FastMCP server over the in-memory client with a fake addon peer:
verify safety classes, that ``dry_run`` previews without sending a mutation, that
``delete_node`` needs ``confirm``, that preconditions surface structured errors,
and that results map to typed models.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalRequest, ApprovalResponse
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.safety import ApprovalGate
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://m.tscn"})
        case "cmd_get_node_properties":
            if p.get("node_path") == "Ghost":
                return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Ghost'.")
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node2D"})
        case "cmd_create_node":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['parent_path']}/{p['name']}", "created": True}
            )
        case "cmd_rename_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "old_name": "Old",
                    "new_name": p["new_name"],
                    "renamed": True,
                },
            )
        case "cmd_set_node_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "property": p["property"],
                    "value": p["value"],
                    "set": True,
                },
            )
        case "cmd_delete_node":
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "deleted": True})
        case "cmd_attach_script":
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": p["node_path"], "script_path": p["script_path"], "attached": True},
            )
        case "cmd_connect_signal":
            # Mimic the addon: a connection already saved in the scene file is
            # reported as an idempotent success, not a failure (issue #152).
            already = p.get("signal_name") == "ready"
            return ResponseEnvelope.success(
                cmd.id, {**p, "connected": True, "already_connected": already}
            )
        case "cmd_save_scene":
            return ResponseEnvelope.success(cmd.id, {"path": "res://m.tscn", "saved": True})
        case "cmd_create_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {"scene_path": p["scene_path"], "root_type": p["root_type"], "created": True},
            )
        case "cmd_instance_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p.get('name', 'Instance')}",
                    "scene_path": p["scene_path"],
                    "instanced": True,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_mutation_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_scene_edit_create_node"].meta["safety_class"] == "mutating"
    assert tools["godot_scene_edit_set_node_property"].meta["safety_class"] == "mutating"
    assert tools["godot_scene_edit_save_scene"].meta["safety_class"] == "mutating"
    assert tools["godot_scene_edit_delete_node"].meta["safety_class"] == "destructive"


async def test_create_node_real_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["node_path"] == "./Player"
    assert "cmd_create_node" in _commands(conn)


async def test_create_node_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["created"] is False
    # Preview path mirrors the addon: a root child is "Player", not "./Player".
    assert result.structured_content["node_path"] == "Player"
    assert "cmd_create_node" not in _commands(conn)  # nothing was actually created


async def test_connect_signal_reports_already_connected() -> None:
    # Re-connecting a signal that's already saved in the scene must surface as an
    # idempotent success (connected + already_connected), not a false failure.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_connect_signal",
            {
                "source_path": "Player",
                "signal_name": "ready",
                "target_path": "Background",
                "method_name": "_ready",
            },
        )
    assert result.structured_content["connected"] is True
    assert result.structured_content["already_connected"] is True


async def test_connect_signal_fresh_connection_not_marked_already() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_connect_signal",
            {
                "source_path": "Button",
                "signal_name": "pressed",
                "target_path": "Player",
                "method_name": "_on_pressed",
            },
        )
    assert result.structured_content["connected"] is True
    assert result.structured_content["already_connected"] is False


async def test_set_property_maps_value_and_flag() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": "Player", "property": "position", "value": {"x": 1, "y": 2}},
        )
    assert result.structured_content["set"] is True
    assert result.structured_content["value"] == {"x": 1, "y": 2}


# -- suggestions (issue #109) --------------------------------------------------


def _addon_base(cmd: CommandEnvelope) -> ResponseEnvelope:
    """Handle bootstrap commands and node checks for suggestion tests."""
    if cmd.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://main.tscn"})
    if cmd.command == "cmd_get_node_properties":
        return ResponseEnvelope.success(
            cmd.id, {"node_path": cmd.params["node_path"], "type": "Node2D"}
        )
    # Return failure for bootstrap commands so FakeAddonConnection auto-replaces
    # cmd_ping / cmd_get_project_info with its default responder.
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", f"Unknown command '{cmd.command}'.")


def _respond_with_suggestions(cmd: CommandEnvelope) -> ResponseEnvelope:
    if cmd.command == "cmd_get_node_property_list":
        return ResponseEnvelope.success(
            cmd.id,
            {
                "node_path": cmd.params["node_path"],
                "type": "CharacterBody2D",
                "properties": [
                    "position",
                    "position_smoothing_enabled",
                    "global_position",
                ],
            },
        )
    if cmd.command == "cmd_set_node_property":
        return ResponseEnvelope.failure(
            cmd.id,
            "VALIDATION_ERROR",
            "Node has no property '{}'.".format(cmd.params.get("property")),
        )
    return _addon_base(cmd)


async def test_set_node_property_suggests_closest_matches() -> None:
    conn = FakeAddonConnection(responder=_respond_with_suggestions)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": "Player", "property": "positoin", "value": 1},
            raise_on_error=False,
        )
    assert result.is_error
    text = str(result.content)
    assert "position" in text
    assert "suggestions=" in text


async def test_set_node_property_no_suggestions_when_list_empty() -> None:
    def _empty(cmd: CommandEnvelope) -> ResponseEnvelope:
        if cmd.command == "cmd_get_node_property_list":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": cmd.params["node_path"], "properties": []}
            )
        if cmd.command == "cmd_set_node_property":
            return ResponseEnvelope.failure(
                cmd.id, "VALIDATION_ERROR", "Node has no property 'bad'."
            )
        return _addon_base(cmd)

    conn = FakeAddonConnection(responder=_empty)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": "Player", "property": "bad", "value": 1},
            raise_on_error=False,
        )
    assert result.is_error
    text = str(result.content)
    assert "has no property 'bad'" in text
    # No suggestions bracket when the list is empty.
    assert "suggestions=" not in text


async def test_delete_node_blocked_when_approval_denied() -> None:
    # With an approval webhook configured and the verdict "deny", a confirmed
    # delete must be blocked BEFORE reaching the bridge (issue #153).
    async def deny(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
        return ApprovalResponse(approved=False, reason="blocked by reviewer")

    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    gate = ApprovalGate(webhook_url="http://hook", poster=deny)
    server = create_server(ServerConfig(), bridge=bridge, approval=gate)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Player", "confirm": True},
            raise_on_error=False,
        )
    assert result.is_error
    assert "APPROVAL_DENIED" in str(result.content)
    assert "blocked by reviewer" in str(result.content)
    assert "cmd_delete_node" not in _commands(conn)  # never reached the addon


async def test_delete_node_proceeds_when_approval_granted() -> None:
    async def approve(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
        return ApprovalResponse(approved=True)

    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    gate = ApprovalGate(webhook_url="http://hook", poster=approve)
    server = create_server(ServerConfig(), bridge=bridge, approval=gate)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node", {"node_path": "Player", "confirm": True}
        )
    assert result.structured_content["deleted"] is True
    assert "cmd_delete_node" in _commands(conn)


async def test_delete_without_confirm_is_blocked() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node", {"node_path": "Player"}, raise_on_error=False
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_delete_node" not in _commands(conn)  # never reached the addon


async def test_delete_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node", {"node_path": "Player", "confirm": True}
        )
    assert result.structured_content["deleted"] is True
    assert "cmd_delete_node" in _commands(conn)


async def test_delete_dry_run_needs_no_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node", {"node_path": "Player", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["deleted"] is False
    assert "cmd_delete_node" not in _commands(conn)


async def test_missing_node_precondition_is_structured_error() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": "Ghost", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)
    assert "cmd_create_node" not in _commands(conn)


# --- instance_scene (issue #80) ------------------------------------------------


async def test_instance_scene_safety_class_is_mutating() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_scene_edit_instance_scene"].meta["safety_class"] == "mutating"


async def test_instance_scene_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_instance_scene",
            {"parent_path": ".", "scene_path": "res://player.tscn"},
        )
    assert result.structured_content["instanced"] is True
    assert result.structured_content["scene_path"] == "res://player.tscn"
    assert "cmd_instance_scene" in _commands(conn)


async def test_instance_scene_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_instance_scene",
            {"parent_path": ".", "scene_path": "res://player.tscn", "name": "P1", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["instanced"] is False
    assert "cmd_instance_scene" not in _commands(conn)


async def test_instance_scene_missing_parent_is_error() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_instance_scene",
            {"parent_path": "Ghost", "scene_path": "res://player.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)
    assert "cmd_instance_scene" not in _commands(conn)
