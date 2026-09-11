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
                    "assigned": True,
                    "persisted": True,
                },
            )
        case "cmd_set_shader_param":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "name": p["name"],
                    "value": p.get("value"),
                    "set": True,
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


async def test_assign_material_on_instanced_child_reports_persistence_truth() -> None:
    """#458/#415: a target inside a non-editable instance renders live but never
    saves — the response must say so (persisted:false + reason) instead of a
    success tone that reads as persisted."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_assign_shader_material":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "shader_path": cmd.params["shader_path"],
                    "material_property": "material_override",
                    "assigned": True,
                    "persisted": False,
                    "reason": "instanced_child_not_editable",
                    "hint": "Enable Editable Children on the instance, or target a "
                    "scene-owned node — this change will not save.",
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": "Relic4/Visual/Orb", "shader_path": "res://fx.gdshader"},
        )
    sc = result.structured_content
    assert sc["assigned"] is True
    assert sc["persisted"] is False
    assert sc["reason"] == "instanced_child_not_editable"
    assert "not save" in sc["hint"]


async def test_assign_material_persists_for_scene_owned_node() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_assign_shader_material":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "shader_path": cmd.params["shader_path"],
                    "material_property": "material",
                    "assigned": True,
                    "persisted": True,
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": "Sprite2D", "shader_path": "res://fx.gdshader"},
        )
    sc = result.structured_content
    assert sc["assigned"] is True
    assert sc["persisted"] is True


async def test_set_param_reports_landed_value_read_back() -> None:
    """#460: set:true must reflect the landed value (read-back after commit),
    not echo the requested value."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_set_shader_param":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "name": cmd.params["name"],
                    "value": 0.5,
                    "set": True,
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": "Sprite2D", "name": "strength", "value": 0.5, "param_type": "float"},
        )
    sc = result.structured_content
    assert sc["set"] is True
    assert sc["value"] == 0.5


async def test_dry_run_preview_carries_persistence_truth() -> None:
    """#458 round-2: the dry-run preview must be honest about persistence — it
    probes `cmd_node_persistence` read-only and reports the instanced-child
    reason instead of hardcoding persisted:true."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_node_persistence":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "persisted": False,
                    "reason": "instanced_child_not_editable",
                    "hint": "the change will not save",
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        dry = await client.call_tool(
            "godot_shader_assign_material",
            {"node_path": "Relic4/Visual/Orb", "shader_path": "res://fx.gdshader", "dry_run": True},
        )
    sc = dry.structured_content
    assert sc["dry_run"] is True
    assert sc["assigned"] is False
    assert sc["persisted"] is False
    assert sc["reason"] == "instanced_child_not_editable"
    sent = [CommandEnvelope.model_validate_json(s).command for s in conn.sent]
    assert "cmd_node_persistence" in sent  # the honest preview paid one read-only probe
    assert "cmd_assign_shader_material" not in sent


async def test_set_param_not_declared_is_a_structured_error() -> None:
    """#460 round-2: a param that isn't declared on the shader reads back null —
    the set did not land, which is a structured error (not a success envelope
    with set:false)."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_set_shader_param":
            return ResponseEnvelope.failure(
                cmd.id,
                "VALIDATION_ERROR",
                "Uniform 'nope' is not declared on the material's shader; the set "
                "did not land (reads back null). Declare the uniform on the shader first.",
                required="param",
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": "Sprite2D", "name": "nope", "value": 0.5, "param_type": "float"},
            raise_on_error=False,
        )
    assert result.is_error
    text = str(result.content)
    assert "VALIDATION_ERROR" in text
    assert "did not land" in text
    assert "param" in text  # [required=param] suffix


async def test_set_param_persistence_truth_still_carries_on_success() -> None:
    """#458: a *landing* set on an instanced child still carries
    persisted:false + reason — both truths coexist (Qodo #463 round-2)."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_node_exists":
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        if cmd.command == "cmd_set_shader_param":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": cmd.params["node_path"],
                    "name": cmd.params["name"],
                    "value": 0.5,
                    "set": True,
                    "persisted": False,
                    "reason": "instanced_child_not_editable",
                    "hint": "the change will not save",
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_set_param",
            {"node_path": "Relic4/Visual/Orb", "name": "strength", "value": 0.5},
        )
    sc = result.structured_content
    assert sc["set"] is True
    assert sc["value"] == 0.5
    assert sc["persisted"] is False
    assert sc["reason"] == "instanced_child_not_editable"
