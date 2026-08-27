"""Contract tests for composite/macro tools (issue #154).

Composite tools collapse multi-step workflows into one bridge round-trip that
the addon executes as a single UndoRedo action. These pin the typed I/O, the
safety class + gated category, and that ``dry_run`` previews without mutating —
driven by a fake addon peer, no live editor.
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
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
            if p.get("node_path") == "Ghost":
                return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Ghost'.")
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        case "cmd_compose_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}".lstrip("./"),
                    "created": True,
                    "children": [c["name"] for c in p.get("children", [])],
                    "script_attached": bool(p.get("script_path")),
                    "properties_set": list(p.get("properties", {}).keys()),
                    "saved": bool(p.get("save")),
                },
            )
        case "cmd_batch_create_nodes":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "created": list(p.get("names", [])),
                    "count": len(p.get("names", [])),
                    "saved": bool(p.get("save")),
                },
            )
        case "cmd_apply_node_edits":
            edits = p.get("edits", [])
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "edited": [e["node_path"] for e in edits],
                    "skipped": [],
                    "count": len(edits),
                    "saved": bool(p.get("save")),
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_composite_tools_are_gated_mutating() -> None:
    names = (
        "godot_composite_compose_node",
        "godot_composite_batch_create_nodes",
        "godot_composite_apply_node_edits",
    )
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        # Gated off by default: absent until the toolset is enabled.
        before = {t.name for t in await client.list_tools()}
        assert before.isdisjoint(names), "composite tools must be gated off by default"
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        tools = {t.name: t for t in await client.list_tools()}
    for name in names:
        assert tools[name].meta["safety_class"] == "mutating"


async def test_compose_node_routes_with_full_config() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_compose_node",
            {
                "parent_path": ".",
                "node_type": "Node2D",
                "node_name": "Hero",
                "properties": {"position": {"x": 10, "y": 20}},
                "script_path": "res://scripts/hero.gd",
                "children": [{"node_type": "Sprite2D", "node_name": "Body"}],
                "save": True,
            },
        )
    data = result.structured_content
    assert data["node_path"] == "Hero"
    assert data["children"] == ["Body"]
    assert data["script_attached"] is True
    assert data["properties_set"] == ["position"]
    assert data["saved"] is True
    assert "cmd_compose_node" in _commands(conn)


async def test_compose_node_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_compose_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Hero", "dry_run": True},
        )
    assert result.structured_content["created"] is False
    assert "cmd_compose_node" not in _commands(conn)


async def test_compose_node_missing_parent_is_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_compose_node",
            {"parent_path": "Ghost", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_batch_create_nodes_routes() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_batch_create_nodes",
            {"parent_path": ".", "node_type": "Sprite2D", "names": ["A", "B", "C"]},
        )
    assert result.structured_content["count"] == 3
    assert result.structured_content["created"] == ["A", "B", "C"]
    assert "cmd_batch_create_nodes" in _commands(conn)


async def test_apply_node_edits_routes() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_apply_node_edits",
            {
                "edits": [
                    {"node_path": "A", "properties": {"visible": False}},
                    {"node_path": "B", "properties": {"modulate": [1, 0, 0, 1]}},
                ]
            },
        )
    assert result.structured_content["count"] == 2
    assert result.structured_content["edited"] == ["A", "B"]
    assert "cmd_apply_node_edits" in _commands(conn)
