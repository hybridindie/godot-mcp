"""Contract tests for visual shader tools (issue #107).

Five tools in a new ``visual_shader`` toolset (gated off by default):
create_visual_shader, add_shader_node, connect_shader_nodes,
set_shader_node_param, list_shader_node_types.
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
        case "cmd_create_visual_shader":
            path = p.get("path", "")
            if not path:
                path = f"res://shaders/{p['name']}.tres"
            return ResponseEnvelope.success(
                cmd.id,
                {"path": path, "created": True},
            )
        case "cmd_add_shader_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_id": p["node_id"],
                    "node_type": p["node_type"],
                    "added": True,
                },
            )
        case "cmd_connect_shader_nodes":
            return ResponseEnvelope.success(cmd.id, {"connected": True})
        case "cmd_set_shader_node_param":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_id": p["node_id"],
                    "property": p["property"],
                    "value": p["value"],
                    "set": True,
                },
            )
        case "cmd_list_shader_node_types":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "types": [
                        "VisualShaderNodeColorConstant",
                        "VisualShaderNodeFloatConstant",
                        "VisualShaderNodeTexture",
                    ]
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_visual_shader_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "create_visual_shader" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "create_visual_shader",
        "add_shader_node",
        "connect_shader_nodes",
        "set_shader_node_param",
        "list_shader_node_types",
    } <= names


async def test_create_visual_shader() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "create_visual_shader",
            {"name": "fire", "type": "3d", "path": "res://shaders/fire.tres"},
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["path"] == "res://shaders/fire.tres"
    assert "cmd_create_visual_shader" in _commands(conn)


async def test_create_visual_shader_defaults() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "create_visual_shader", {"name": "water"}
        )
    assert result.structured_content["path"] == "res://shaders/water.tres"


async def test_add_shader_node() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "add_shader_node",
            {
                "shader_path": "res://shaders/fire.tres",
                "node_type": "VisualShaderNodeColorConstant",
                "node_id": 1,
                "position": [100, 200],
            },
        )
    assert result.structured_content["added"] is True
    assert result.structured_content["node_id"] == 1
    assert result.structured_content["node_type"] == "VisualShaderNodeColorConstant"
    assert "cmd_add_shader_node" in _commands(conn)


async def test_connect_shader_nodes() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "connect_shader_nodes",
            {
                "shader_path": "res://shaders/fire.tres",
                "from_node": 1,
                "from_port": 0,
                "to_node": 0,
                "to_port": 0,
            },
        )
    assert result.structured_content["connected"] is True
    assert "cmd_connect_shader_nodes" in _commands(conn)


async def test_set_shader_node_param() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "set_shader_node_param",
            {
                "shader_path": "res://shaders/fire.tres",
                "node_id": 1,
                "property": "constant",
                "value": {"r": 1.0, "g": 0.5, "b": 0.0},
            },
        )
    assert result.structured_content["set"] is True
    assert result.structured_content["node_id"] == 1
    assert "cmd_set_shader_node_param" in _commands(conn)


async def test_list_shader_node_types_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool("list_shader_node_types")
    assert result.structured_content["types"]
    assert isinstance(result.structured_content["types"], list)


async def test_mutating_tools_have_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "visual_shader"})
        dry = await client.call_tool(
            "add_shader_node",
            {
                "shader_path": "res://shaders/x.tres",
                "node_type": "VisualShaderNodeFloatConstant",
                "node_id": 5,
                "position": [0, 0],
                "dry_run": True,
            },
        )
    assert dry.structured_content["dry_run"] is True
    assert dry.structured_content["added"] is False
    assert "cmd_add_shader_node" not in _commands(conn)
