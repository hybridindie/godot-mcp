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
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
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
            return ResponseEnvelope.success(cmd.id, {**p, "connected": True})
        case "cmd_save_scene":
            return ResponseEnvelope.success(cmd.id, {"path": "res://m.tscn", "saved": True})
        case "cmd_create_scene":
            return ResponseEnvelope.success(
                cmd.id,
                {"scene_path": p["scene_path"], "root_type": p["root_type"], "created": True},
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
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["create_node"].meta["safety_class"] == "mutating"
    assert tools["set_node_property"].meta["safety_class"] == "mutating"
    assert tools["save_scene"].meta["safety_class"] == "mutating"
    assert tools["delete_node"].meta["safety_class"] == "destructive"


async def test_create_node_real_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool(
            "create_node", {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"}
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["node_path"] == "./Player"
    assert "cmd_create_node" in _commands(conn)


async def test_create_node_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool(
            "create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["created"] is False
    assert "cmd_create_node" not in _commands(conn)  # nothing was actually created


async def test_set_property_maps_value_and_flag() -> None:
    server, _ = _build()
    async with Client(server) as client:
        result = await client.call_tool(
            "set_node_property",
            {"node_path": "Player", "property": "position", "value": {"x": 1, "y": 2}},
        )
    assert result.structured_content["set"] is True
    assert result.structured_content["value"] == {"x": 1, "y": 2}


async def test_delete_without_confirm_is_blocked() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool(
            "delete_node", {"node_path": "Player"}, raise_on_error=False
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_delete_node" not in _commands(conn)  # never reached the addon


async def test_delete_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool("delete_node", {"node_path": "Player", "confirm": True})
    assert result.structured_content["deleted"] is True
    assert "cmd_delete_node" in _commands(conn)


async def test_delete_dry_run_needs_no_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool("delete_node", {"node_path": "Player", "dry_run": True})
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["deleted"] is False
    assert "cmd_delete_node" not in _commands(conn)


async def test_missing_node_precondition_is_structured_error() -> None:
    server, conn = _build()
    async with Client(server) as client:
        result = await client.call_tool(
            "create_node",
            {"parent_path": "Ghost", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)
    assert "cmd_create_node" not in _commands(conn)
