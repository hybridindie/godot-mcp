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
        case "cmd_read_visual_shader":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "shader_path": p["shader_path"],
                    "mode": "spatial",
                    "nodes": [
                        {
                            "id": 0,
                            "type": "VisualShaderNodeOutput",
                            "position": {"x": 0.0, "y": 0.0},
                            "parameters": {},
                        },
                        {
                            "id": 2,
                            "type": "VisualShaderNodeColorConstant",
                            "position": {"x": -200.0, "y": 40.0},
                            "parameters": {"constant": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}},
                        },
                    ],
                    "connections": [{"from_node": 2, "from_port": 0, "to_node": 0, "to_port": 0}],
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
        assert "godot_visual_shader_create" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "godot_visual_shader_create",
        "godot_visual_shader_add_node",
        "godot_visual_shader_connect_nodes",
        "godot_visual_shader_set_node_param",
        "godot_visual_shader_list_node_types",
    } <= names


async def test_create_visual_shader() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_create",
            {"name": "fire", "type": "3d", "path": "res://shaders/fire.tres"},
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["path"] == "res://shaders/fire.tres"
    assert "cmd_create_visual_shader" in _commands(conn)


async def test_create_visual_shader_defaults() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool("godot_visual_shader_create", {"name": "water"})
    assert result.structured_content["path"] == "res://shaders/water.tres"


async def test_add_shader_node() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_add_node",
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
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_connect_nodes",
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
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_set_node_param",
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
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool("godot_visual_shader_list_node_types")
    assert result.structured_content["types"]
    assert isinstance(result.structured_content["types"], list)


async def test_mutating_tools_have_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        dry = await client.call_tool(
            "godot_visual_shader_add_node",
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


async def test_read_visual_shader_returns_graph() -> None:
    # #219 G6: read the VisualShader graph (nodes + connections) — inverts the writers.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_read", {"shader_path": "res://shaders/fx.tres"}
        )
        tools = {t.name: t for t in await client.list_tools()}
    data = result.structured_content
    assert data["mode"] == "spatial"
    assert {n["id"] for n in data["nodes"]} == {0, 2}
    color = next(n for n in data["nodes"] if n["id"] == 2)
    assert color["type"] == "VisualShaderNodeColorConstant"
    assert color["parameters"]["constant"]["r"] == 1.0
    conn_edge = data["connections"][0]
    assert conn_edge["from_node"] == 2 and conn_edge["to_node"] == 0
    assert tools["godot_visual_shader_read"].meta["safety_class"] == "read_only"
    assert "cmd_read_visual_shader" in _commands(conn)
