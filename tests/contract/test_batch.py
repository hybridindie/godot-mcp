"""Contract tests for batch / refactor tools (issue #48)."""

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
        case "cmd_get_active_scene":  # require_active_scene precondition
            return ResponseEnvelope.success(cmd.id, {"is_open": True})
        case "cmd_find_nodes_by_type":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "type": p["type"],
                    "nodes": [
                        {"path": "Sprite", "name": "Sprite", "type": "Sprite2D"},
                        {"path": "UI/Icon", "name": "Icon", "type": "Sprite2D"},
                    ],
                    "count": 2,
                },
            )
        case "cmd_batch_set_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "property": p["property"],
                    "applied": ["Sprite", "UI/Icon"],
                    "skipped": [{"path": "Plain", "reason": "no such property"}],
                    "count": 2,
                    "dry_run": p.get("dry_run", False),
                },
            )
        case "cmd_cross_scene_set_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "results": [{"scene": s, "modified": 1, "error": ""} for s in p["scenes"]],
                    "total_modified": len(p["scenes"]),
                    "scenes": len(p["scenes"]),
                    "dry_run": p.get("dry_run", False),
                },
            )
        case "cmd_get_dependencies":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "path": p["path"],
                    "dependencies": [
                        {
                            "raw": "uid://abc::res://icon.png::Texture2D",
                            "path": "res://icon.png",
                            "type": "Texture2D",
                        }
                    ],
                    "count": 1,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "batch_set_property" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "batch"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "find_nodes_by_type",
        "batch_set_property",
        "cross_scene_set_property",
        "get_dependencies",
    }
    assert expected <= set(tools)
    assert tools["batch_set_property"].meta["safety_class"] == "mutating"
    assert tools["cross_scene_set_property"].meta["safety_class"] == "mutating"
    assert tools["find_nodes_by_type"].meta["safety_class"] == "read_only"
    assert tools["get_dependencies"].meta["safety_class"] == "read_only"


async def test_find_and_batch_set() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "batch"})
        found = await client.call_tool("find_nodes_by_type", {"node_type": "Sprite2D"})
        result = await client.call_tool(
            "batch_set_property",
            {"property": "visible", "value": False, "node_type": "Sprite2D"},
        )
    assert found.structured_content["count"] == 2
    assert found.structured_content["nodes"][0]["type"] == "Sprite2D"
    assert result.structured_content["count"] == 2
    assert result.structured_content["skipped"][0]["reason"] == "no such property"


async def test_cross_scene_and_dependencies() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "batch"})
        cross = await client.call_tool(
            "cross_scene_set_property",
            {
                "scenes": ["res://a.tscn", "res://b.tscn"],
                "node_type": "Camera2D",
                "property": "enabled",
                "value": True,
            },
        )
        deps = await client.call_tool("get_dependencies", {"path": "res://main.tscn"})
    assert cross.structured_content["total_modified"] == 2
    assert cross.structured_content["results"][0]["scene"] == "res://a.tscn"
    assert deps.structured_content["dependencies"][0]["path"] == "res://icon.png"


async def test_batch_set_dry_run_forwards_flag() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "batch"})
        result = await client.call_tool(
            "batch_set_property",
            {"property": "visible", "value": False, "node_type": "Sprite2D", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    # dry_run is forwarded to the addon (which computes the plan), not short-circuited
    assert "cmd_batch_set_property" in _commands(conn)
