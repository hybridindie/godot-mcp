"""Contract tests for node-parity tools (issue #31)."""

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
        case "cmd_get_node_properties":  # used by require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node"})
        case "cmd_duplicate_node":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['node_path']}2", "source_path": p["node_path"]}
            )
        case "cmd_move_node":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['new_parent_path']}/X", "moved": True}
            )
        case "cmd_add_to_group":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "group": p["group"], "added": True}
            )
        case "cmd_remove_from_group":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "group": p["group"], "removed": True}
            )
        case "cmd_list_signal_connections":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "connections": [
                        {
                            "signal": "timeout",
                            "target_path": ".",
                            "method": "queue_free",
                            "persistent": True,
                        }
                    ],
                },
            )
        case "cmd_disconnect_signal":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "source_path": p["source_path"],
                    "signal_name": p["signal_name"],
                    "target_path": p["target_path"],
                    "method_name": p["method_name"],
                    "disconnected": True,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_node_ops_gated_in_scene_edit() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_scene_edit_duplicate_node" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "godot_scene_edit_duplicate_node",
        "godot_scene_edit_move_node",
        "godot_scene_edit_add_to_group",
        "godot_scene_edit_remove_from_group",
        "godot_scene_edit_list_signal_connections",
        "godot_scene_edit_disconnect_signal",
    } <= names


async def test_duplicate_and_move() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        dup = await client.call_tool("godot_scene_edit_duplicate_node", {"node_path": "Box"})
        mv = await client.call_tool(
            "godot_scene_edit_move_node", {"node_path": "Box", "new_parent_path": "Container"}
        )
    assert dup.structured_content["node_path"] == "Box2"
    assert mv.structured_content["moved"] is True


async def test_group_tools() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        added = await client.call_tool(
            "godot_scene_edit_add_to_group", {"node_path": "Box", "group": "g"}
        )
        removed = await client.call_tool(
            "godot_scene_edit_remove_from_group", {"node_path": "Box", "group": "g"}
        )
    assert added.structured_content == {
        "node_path": "Box",
        "group": "g",
        "in_group": True,
        "changed": True,
        "dry_run": False,
    }
    assert removed.structured_content["in_group"] is False


async def test_list_and_disconnect_signals() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        listed = await client.call_tool(
            "godot_scene_edit_list_signal_connections", {"node_path": "Clock"}
        )
        tool = next(
            t
            for t in await client.list_tools()
            if t.name == "godot_scene_edit_list_signal_connections"
        )
        disc = await client.call_tool(
            "godot_scene_edit_disconnect_signal",
            {
                "source_path": "Clock",
                "signal_name": "timeout",
                "target_path": ".",
                "method_name": "queue_free",
            },
        )
    assert tool.meta is not None and tool.meta.get("safety_class") == "read_only"
    assert listed.structured_content["connections"][0]["method"] == "queue_free"
    assert disc.structured_content["disconnected"] is True


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_duplicate_node", {"node_path": "Box", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_duplicate_node" not in _commands(conn)
