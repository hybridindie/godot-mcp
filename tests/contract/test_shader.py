"""Contract tests for shader tools (issue #47)."""

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
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "type": "Sprite2D"}
            )
        case "cmd_create_shader":
            return ResponseEnvelope.success(
                cmd.id, {"shader_path": p["shader_path"], "created": True}
            )
        case "cmd_read_shader":
            return ResponseEnvelope.success(
                cmd.id, {"shader_path": p["shader_path"], "code": "shader_type canvas_item;"}
            )
        case "cmd_assign_shader_material":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "shader_path": p["shader_path"],
                    "material_property": "material",
                },
            )
        case "cmd_set_shader_param":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "name": p["name"]}
            )
        case "cmd_get_shader_param":
            if p.get("name") == "missing":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "node_path": p["node_path"],
                        "name": p["name"],
                        "value": None,
                        "exists": False,
                    },
                )
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": p["node_path"], "name": p["name"], "value": 2.0, "exists": True},
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_shader_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_shader_create" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        tools = {t.name: t for t in await client.list_tools()}
    mutating = {"godot_shader_create", "godot_shader_assign_material", "godot_shader_set_param"}
    assert mutating <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in mutating)
    assert tools["godot_shader_read"].meta["safety_class"] == "read_only"


async def test_create_read_assign_set() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        created = await client.call_tool(
            "godot_shader_create", {"shader_path": "res://fx.gdshader"}
        )
        read = await client.call_tool("godot_shader_read", {"shader_path": "res://fx.gdshader"})
        assigned = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": "Sprite2D", "shader_path": "res://fx.gdshader"},
        )
        param = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": "Sprite2D", "name": "strength", "value": 0.5, "param_type": "float"},
        )
    assert created.structured_content["created"] is True
    assert read.structured_content["code"].startswith("shader_type")
    assert assigned.structured_content["material_property"] == "material"
    assert param.structured_content["name"] == "strength"


async def test_default_code_passed_when_omitted() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        await client.call_tool("godot_shader_create", {"shader_path": "res://fx.gdshader"})
    sent = [
        CommandEnvelope.model_validate_json(s)
        for s in conn.sent
        if CommandEnvelope.model_validate_json(s).command == "cmd_create_shader"
    ]
    assert "shader_type canvas_item;" in sent[0].params["code"]


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_create", {"shader_path": "res://fx.gdshader", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_create_shader" not in _commands(conn)


async def test_get_shader_param_returns_value() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_get_param", {"node_path": "Sprite2D", "name": "strength"}
        )
    assert result.structured_content["value"] == 2.0
    assert result.structured_content["exists"] is True


async def test_get_shader_param_nonexistent_returns_exists_false() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_get_param", {"node_path": "Sprite2D", "name": "missing"}
        )
    assert result.structured_content["exists"] is False


async def test_get_shader_param_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        grouped = await client.call_tool(
            "godot_list_tools_by_safety_class", {}
        )
    assert "godot_shader_get_param" in grouped.structured_content["read_only"]
