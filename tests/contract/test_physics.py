"""Contract tests for physics tools (issue #41)."""

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
        case "cmd_setup_physics_body":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "properties": {"mass": 5.0}}
            )
        case "cmd_setup_collision":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['node_path']}/Col",
                    "shape_type": p["shape_type"],
                    "created": True,
                },
            )
        case "cmd_set_physics_layers":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "collision_layer": 5, "collision_mask": 2}
            )
        case "cmd_add_raycast":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['parent_path']}/{p['name']}", "created": True}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_physics_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_physics_setup_collision" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "physics"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_physics_setup_body",
        "godot_physics_setup_collision",
        "godot_physics_set_layers",
        "godot_physics_add_raycast",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_setup_collision_and_layers() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "physics"})
        col = await client.call_tool(
            "godot_physics_setup_collision",
            {
                "node_path": "Body",
                "shape_type": "RectangleShape2D",
                "properties": {"size": {"x": 32, "y": 32}},
            },
        )
        layers = await client.call_tool(
            "godot_physics_set_layers", {"node_path": "Body", "layers": [1, 3], "mask": [2]}
        )
    assert col.structured_content["created"] is True
    assert layers.structured_content["collision_layer"] == 5
    assert layers.structured_content["collision_mask"] == 2


async def test_setup_body_and_raycast() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "physics"})
        body = await client.call_tool(
            "godot_physics_setup_body", {"node_path": "Body", "properties": {"mass": 5}}
        )
        ray = await client.call_tool(
            "godot_physics_add_raycast",
            {
                "parent_path": ".",
                "name": "Ray",
                "properties": {"target_position": "Vector2(0,100)"},
            },
        )
    assert body.structured_content["properties"]["mass"] == 5.0
    assert ray.structured_content["node_path"] == "./Ray"


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "physics"})
        result = await client.call_tool(
            "godot_physics_set_layers", {"node_path": "Body", "layers": [1], "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_set_physics_layers" not in _commands(conn)
