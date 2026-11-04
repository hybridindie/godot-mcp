"""Contract tests for VisualShader node groups/subgraphs (issue #601).

Godot 4.8 adds ``VisualShaderGroup`` / ``VisualShaderNodeGroup``. The five group
verbs live in the existing ``visual_shader`` toolset and are gated in the addon:
on 4.4–4.7 every call returns a structured ``UNSUPPORTED`` envelope instead of
a silent no-op. The 4.8 success path is exercised by the addon smoke on the
advisory 4.8 lane.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

GROUP_TOOLS = {
    "godot_visual_shader_create_group",
    "godot_visual_shader_rename_group",
    "godot_visual_shader_remove_group",
    "godot_visual_shader_add_group_node",
    "godot_visual_shader_remove_group_node",
}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_create_shader_group":
            return ResponseEnvelope.success(
                cmd.id, {"node_id": p["node_id"], "name": p["name"], "created": True}
            )
        case "cmd_rename_shader_group":
            return ResponseEnvelope.success(
                cmd.id, {"node_id": p["node_id"], "name": p["name"], "renamed": True}
            )
        case "cmd_remove_shader_group":
            return ResponseEnvelope.success(
                cmd.id, {"node_id": p["node_id"], "name": "fx", "removed": True}
            )
        case "cmd_add_shader_group_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "group_node_id": p["group_node_id"],
                    "node_id": p["node_id"],
                    "node_type": p["node_type"],
                    "added": True,
                },
            )
        case "cmd_remove_shader_group_node":
            return ResponseEnvelope.success(
                cmd.id,
                {"group_node_id": p["group_node_id"], "node_id": p["node_id"], "removed": True},
            )
        case "cmd_read_visual_shader":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "shader_path": p["shader_path"],
                    "mode": "spatial",
                    "nodes": [
                        {
                            "id": 2,
                            "type": "VisualShaderNodeGroup",
                            "position": {"x": 0.0, "y": 0.0},
                            "parameters": {},
                        }
                    ],
                    "connections": [],
                    "groups": [
                        {
                            "node_id": 2,
                            "name": "fx",
                            "members": [
                                {
                                    "id": 0,
                                    "type": "VisualShaderNodeFloatConstant",
                                    "position": {"x": 10.0, "y": 20.0},
                                    "parameters": {},
                                    "group": 2,
                                }
                            ],
                        }
                    ],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _unsupported_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command in {
        "cmd_create_shader_group",
        "cmd_rename_shader_group",
        "cmd_remove_shader_group",
        "cmd_add_shader_group_node",
        "cmd_remove_shader_group_node",
    }:
        return ResponseEnvelope.failure(
            cmd.id,
            "UNSUPPORTED",
            "VisualShader node groups require Godot 4.8+; this editor is 4.7.2.",
            required="godot_version",
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build(
    responder: Callable[[CommandEnvelope], ResponseEnvelope | None] = _responder,
) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _envelopes(conn: FakeAddonConnection) -> list[CommandEnvelope]:
    return [CommandEnvelope.model_validate_json(s) for s in conn.sent]


def _params_for(conn: FakeAddonConnection, command: str) -> dict[str, object]:
    return next(e.params for e in _envelopes(conn) if e.command == command)


async def test_group_tools_are_gated_in_visual_shader_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert not (GROUP_TOOLS & {t.name for t in await client.list_tools()})
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        names = {t.name for t in await client.list_tools()}
    assert GROUP_TOOLS <= names


async def test_create_group_sends_expected_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_create_group",
            {
                "shader_path": "res://shaders/fx.tres",
                "name": "fx",
                "node_id": 3,
                "position": [12, 34],
            },
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["node_id"] == 3
    assert result.structured_content["name"] == "fx"
    params = _params_for(conn, "cmd_create_shader_group")
    assert params == {
        "shader_path": "res://shaders/fx.tres",
        "name": "fx",
        "node_id": 3,
        "position": [12, 34],
    }


async def test_rename_group_sends_expected_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_rename_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3, "name": "glow"},
        )
    assert result.structured_content["renamed"] is True
    assert result.structured_content["name"] == "glow"
    params = _params_for(conn, "cmd_rename_shader_group")
    assert params == {
        "shader_path": "res://shaders/fx.tres",
        "node_id": 3,
        "name": "glow",
    }


async def test_add_group_node_sends_expected_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_add_group_node",
            {
                "shader_path": "res://shaders/fx.tres",
                "group_node_id": 3,
                "node_type": "VisualShaderNodeFloatConstant",
                "node_id": 0,
                "position": [5, 6],
            },
        )
    assert result.structured_content["added"] is True
    assert result.structured_content["group_node_id"] == 3
    params = _params_for(conn, "cmd_add_shader_group_node")
    assert params == {
        "shader_path": "res://shaders/fx.tres",
        "group_node_id": 3,
        "node_type": "VisualShaderNodeFloatConstant",
        "node_id": 0,
        "position": [5, 6],
    }


async def test_remove_group_requires_confirmation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        blocked = await client.call_tool(
            "godot_visual_shader_remove_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3},
            raise_on_error=False,
        )
        assert blocked.is_error and "confirm" in str(blocked.content)
        assert not [e for e in _envelopes(conn) if e.command == "cmd_remove_shader_group"]

        result = await client.call_tool(
            "godot_visual_shader_remove_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3, "confirm": True},
        )
    assert result.structured_content["removed"] is True
    assert _params_for(conn, "cmd_remove_shader_group")["node_id"] == 3


async def test_remove_group_node_requires_confirmation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        blocked = await client.call_tool(
            "godot_visual_shader_remove_group_node",
            {"shader_path": "res://shaders/fx.tres", "group_node_id": 3, "node_id": 0},
            raise_on_error=False,
        )
        assert blocked.is_error and "confirm" in str(blocked.content)
        assert not [e for e in _envelopes(conn) if e.command == "cmd_remove_shader_group_node"]

        result = await client.call_tool(
            "godot_visual_shader_remove_group_node",
            {
                "shader_path": "res://shaders/fx.tres",
                "group_node_id": 3,
                "node_id": 0,
                "confirm": True,
            },
        )
    assert result.structured_content["removed"] is True
    params = _params_for(conn, "cmd_remove_shader_group_node")
    assert params["group_node_id"] == 3 and params["node_id"] == 0


async def test_remove_group_dry_run_previews_without_confirmation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_remove_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3, "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["removed"] is False
    assert not [e for e in _envelopes(conn) if e.command == "cmd_remove_shader_group"]


async def test_read_reports_group_membership() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(
            "godot_visual_shader_read", {"shader_path": "res://shaders/fx.tres"}
        )
    data = result.structured_content
    assert data["nodes"][0]["type"] == "VisualShaderNodeGroup"
    groups = data["groups"]
    assert groups[0]["node_id"] == 2
    assert groups[0]["name"] == "fx"
    member = groups[0]["members"][0]
    assert member["group"] == 2
    assert member["type"] == "VisualShaderNodeFloatConstant"
    assert "cmd_read_visual_shader" in [e.command for e in _envelopes(conn)]


@pytest.mark.parametrize(
    ("tool", "args", "command"),
    [
        (
            "godot_visual_shader_create_group",
            {"shader_path": "res://shaders/fx.tres", "name": "fx", "node_id": 3},
            "cmd_create_shader_group",
        ),
        (
            "godot_visual_shader_rename_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3, "name": "glow"},
            "cmd_rename_shader_group",
        ),
        (
            "godot_visual_shader_remove_group",
            {"shader_path": "res://shaders/fx.tres", "node_id": 3, "confirm": True},
            "cmd_remove_shader_group",
        ),
        (
            "godot_visual_shader_add_group_node",
            {
                "shader_path": "res://shaders/fx.tres",
                "group_node_id": 3,
                "node_type": "VisualShaderNodeFloatConstant",
                "node_id": 0,
            },
            "cmd_add_shader_group_node",
        ),
        (
            "godot_visual_shader_remove_group_node",
            {
                "shader_path": "res://shaders/fx.tres",
                "group_node_id": 3,
                "node_id": 0,
                "confirm": True,
            },
            "cmd_remove_shader_group_node",
        ),
    ],
)
async def test_group_tools_are_unsupported_before_godot_48(
    tool: str, args: dict[str, object], command: str
) -> None:
    # The addon gates on ClassDB.class_exists("VisualShaderGroup"): on 4.4–4.7
    # every group verb returns an actionable UNSUPPORTED envelope.
    server, conn = _build(responder=_unsupported_responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        result = await client.call_tool(tool, args, raise_on_error=False)
    content = str(result.content)
    assert result.is_error and "UNSUPPORTED" in content and "4.8" in content
    assert "required=godot_version" in content
    assert command in [e.command for e in _envelopes(conn)]


async def test_group_tool_safety_classes_and_dry_run() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "visual_shader"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_visual_shader_create_group": "mutating",
        "godot_visual_shader_rename_group": "mutating",
        "godot_visual_shader_add_group_node": "mutating",
        "godot_visual_shader_remove_group": "destructive",
        "godot_visual_shader_remove_group_node": "destructive",
    }
    for name, safety in expected.items():
        assert tools[name].meta["safety_class"] == safety
        assert "dry_run" in tools[name].input_schema["properties"]
