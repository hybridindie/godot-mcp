"""Contract tests for resource-file + autoload tools (issue #34)."""

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
        case "cmd_read_resource":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "resource_path": p["resource_path"],
                    "type": "RectangleShape2D",
                    "script": None,
                    "properties": {"size": {"x": 4.0, "y": 5.0}},
                },
            )
        case "cmd_create_resource":
            return ResponseEnvelope.success(
                cmd.id, {"resource_path": p["resource_path"], "type": p["type"], "created": True}
            )
        case "cmd_set_resource_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "resource_path": p["resource_path"],
                    "property": p["property"],
                    "value": p["value"],
                },
            )
        case "cmd_register_autoload":
            return ResponseEnvelope.success(
                cmd.id, {"name": p["name"], "path": p["path"], "registered": True}
            )
        case "cmd_unregister_autoload":
            return ResponseEnvelope.success(cmd.id, {"name": p["name"], "unregistered": True})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_resources_edit_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "create_resource" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "resources_edit"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "read_resource_file",
        "create_resource",
        "set_resource_property",
        "register_autoload",
        "unregister_autoload",
    } <= names


async def test_read_resource_file() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "read_resource_file", {"resource_path": "res://shape.tres"}
        )
    assert result.structured_content["type"] == "RectangleShape2D"
    assert result.structured_content["properties"]["size"] == {"x": 4.0, "y": 5.0}


async def test_create_resource_safety_and_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "resources_edit"})
        tool = next(t for t in await client.list_tools() if t.name == "create_resource")
        assert tool.meta is not None and tool.meta.get("safety_class") == "mutating"
        dry = await client.call_tool(
            "create_resource",
            {"type": "RectangleShape2D", "resource_path": "res://s.tres", "dry_run": True},
        )
    assert dry.structured_content["dry_run"] is True
    assert "cmd_create_resource" not in _commands(conn)


async def test_set_resource_property_and_autoloads() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "resources_edit"})
        s = await client.call_tool(
            "set_resource_property",
            {"resource_path": "res://s.tres", "property": "size", "value": {"x": 1, "y": 2}},
        )
        reg = await client.call_tool(
            "register_autoload", {"name": "Game", "path": "res://game.gd"}
        )
        unreg = await client.call_tool("unregister_autoload", {"name": "Game"})
    assert s.structured_content["value"] == {"x": 1, "y": 2}
    assert reg.structured_content["registered"] is True
    assert unreg.structured_content["unregistered"] is True


async def test_read_resource_file_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "resources_edit"})
        tool = next(t for t in await client.list_tools() if t.name == "read_resource_file")
    assert tool.meta is not None and tool.meta.get("safety_class") == "read_only"
