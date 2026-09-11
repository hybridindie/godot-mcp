"""Contract tests for shader tools (issue #47)."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# #458: node paths the fake addon treats as non-persistable targets.
INSTANCED_CHILD = "Relic/Orb"  # inside an instance without Editable Children
FOREIGN_MATERIAL = "Relic2/Orb"  # editable child whose material lives in the instanced scene


def _persistence(node_path: str, *, material: bool = False) -> dict[str, Any]:
    """The persistence fields the addon stamps on a shader mutation result (#458)."""
    if node_path == INSTANCED_CHILD:
        return {
            "persisted": False,
            "reason": "instanced_child_not_editable",
            "hint": "Enable Editable Children on 'Relic', or target a node the scene owns.",
        }
    if material and node_path == FOREIGN_MATERIAL:
        return {
            "persisted": False,
            "reason": "material_embedded_in_other_resource",
            "hint": "Edit the material in 'res://relic.tscn', or assign one this scene owns.",
        }
    return {"persisted": True}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
            return ResponseEnvelope.success(cmd.id, {"exists": True})
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
                    **_persistence(p["node_path"]),
                },
            )
        case "cmd_set_shader_param":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "name": p["name"],
                    **_persistence(p["node_path"], material=True),
                },
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
    assert assigned.structured_content["persisted"] is True
    assert assigned.structured_content.get("reason") is None
    assert param.structured_content["name"] == "strength"
    assert param.structured_content["persisted"] is True
    assert param.structured_content.get("reason") is None


async def test_assign_on_instanced_child_reports_not_persisted() -> None:
    """#415: the material IS applied (effect reported) but the result must say it won't save."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": INSTANCED_CHILD, "shader_path": "res://fx.gdshader"},
        )
    content = result.structured_content
    assert content["material_property"] == "material"
    assert content["persisted"] is False
    assert content["reason"] == "instanced_child_not_editable"
    assert "Editable Children" in content["hint"]


async def test_set_param_on_instanced_child_reports_not_persisted() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": INSTANCED_CHILD, "name": "pulse_speed", "value": 3.0},
        )
    content = result.structured_content
    assert content["name"] == "pulse_speed"
    assert content["persisted"] is False
    assert content["reason"] == "instanced_child_not_editable"
    assert content["hint"]


async def test_set_param_on_material_owned_by_other_resource_reports_not_persisted() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": FOREIGN_MATERIAL, "name": "pulse_speed", "value": 3.0},
        )
    content = result.structured_content
    assert content["persisted"] is False
    assert content["reason"] == "material_embedded_in_other_resource"
    assert content["hint"]


async def test_dry_run_leaves_persistence_unknown() -> None:
    """Persistence is only knowable editor-side; a preview must not claim either way."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        assigned = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": INSTANCED_CHILD, "shader_path": "res://fx.gdshader", "dry_run": True},
        )
        param = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": INSTANCED_CHILD, "name": "pulse_speed", "value": 3.0, "dry_run": True},
        )
    for content in (assigned.structured_content, param.structured_content):
        assert content["dry_run"] is True
        assert content.get("persisted") is None
        assert content.get("reason") is None
    sent = _commands(conn)
    assert "cmd_assign_shader_material" not in sent
    assert "cmd_set_shader_param" not in sent


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
    grouped_result = grouped.structured_content["tools_by_safety_class"]["read_only"]
    assert "godot_shader_get_param" in grouped_result
