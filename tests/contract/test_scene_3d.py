"""Contract tests for 3D scene tools (issue #40)."""

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
        case "cmd_get_node_properties":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node"})
        case "cmd_add_mesh_instance":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "mesh_type": p["mesh_type"],
                    "created": True,
                },
            )
        case "cmd_setup_camera":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "current": p["make_current"],
                    "created": True,
                },
            )
        case "cmd_setup_lighting":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "light_type": p["light_type"],
                    "created": True,
                },
            )
        case "cmd_setup_environment":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['parent_path']}/{p['name']}", "created": True}
            )
        case "cmd_gridmap_set_cell":
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": p["node_path"], "position": p["position"], "item": p["item"]},
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_scene_3d_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "add_mesh_instance" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "add_mesh_instance",
        "setup_camera",
        "setup_lighting",
        "setup_environment",
        "gridmap_set_cell",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_mesh_camera_light_environment() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        mesh = await client.call_tool(
            "add_mesh_instance",
            {"parent_path": ".", "mesh_type": "SphereMesh", "properties": {"radius": 2}},
        )
        cam = await client.call_tool(
            "setup_camera", {"parent_path": ".", "properties": {"fov": 60}}
        )
        light = await client.call_tool(
            "setup_lighting", {"parent_path": ".", "light_type": "OmniLight3D"}
        )
        env = await client.call_tool("setup_environment", {"parent_path": "."})
    assert mesh.structured_content["mesh_type"] == "SphereMesh"
    assert mesh.structured_content["created"] is True
    assert cam.structured_content["current"] is True
    assert cam.structured_content["node_path"] == "./Camera3D"
    assert light.structured_content["light_type"] == "OmniLight3D"
    assert light.structured_content["node_path"] == "./OmniLight3D"
    assert env.structured_content["created"] is True


async def test_gridmap_set_cell_roundtrips_position() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        cell = await client.call_tool(
            "gridmap_set_cell", {"node_path": "GridMap", "position": [1, 0, 2], "item": 3}
        )
    assert cell.structured_content["position"] == [1, 0, 2]
    assert cell.structured_content["item"] == 3


async def test_gridmap_missing_library_preserves_required() -> None:
    # When the addon returns a structured precondition (required=mesh_library),
    # route() preserves it so the agent learns what to satisfy.
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_node_properties":
            return ResponseEnvelope.success(cmd.id, {"node_path": "GridMap", "type": "GridMap"})
        if cmd.command == "cmd_gridmap_set_cell":
            return ResponseEnvelope.failure(
                cmd.id, "VALIDATION_ERROR", "GridMap has no mesh_library.", required="mesh_library"
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        result = await client.call_tool(
            "gridmap_set_cell",
            {"node_path": "GridMap", "position": [0, 0, 0], "item": 0},
            raise_on_error=False,
        )
    assert result.is_error
    assert "mesh_library" in str(result.content)


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        result = await client.call_tool(
            "add_mesh_instance", {"parent_path": ".", "mesh_type": "BoxMesh", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_add_mesh_instance" not in _commands(conn)
