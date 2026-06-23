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
        case "cmd_gridmap_get_cell":
            empty = p["position"] == [9, 9, 9]
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "position": p["position"],
                    "item": -1 if empty else 3,
                    "orientation": 0 if empty else 22,
                    "empty": empty,
                },
            )
        case "cmd_create_mesh_library":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path", ""),
                    "library_path": p.get("save_path", ""),
                    "created": True,
                },
            )
        case "cmd_add_mesh_library_item":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path", ""),
                    "library_path": p.get("library_path", ""),
                    "item_id": 0,
                    "name": p.get("name", ""),
                    "mesh_type": p.get("mesh_type", ""),
                    "mesh_path": p.get("mesh_path", ""),
                },
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


async def test_mesh_library_authoring_chain() -> None:
    # Build a MeshLibrary on a GridMap, add an item from a primitive mesh — the
    # prerequisite that lets gridmap_set_cell place a real item.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        tools = {t.name: t for t in await client.list_tools()}
        authoring = {"create_mesh_library", "add_mesh_library_item"}
        assert authoring <= set(tools)
        assert all(tools[n].meta["safety_class"] == "mutating" for n in authoring)
        lib = await client.call_tool("create_mesh_library", {"node_path": "Grid"})
        item = await client.call_tool(
            "add_mesh_library_item",
            {"node_path": "Grid", "mesh_type": "BoxMesh", "name": "Wall"},
        )
    assert lib.structured_content["created"] is True
    assert item.structured_content["item_id"] == 0
    assert item.structured_content["mesh_type"] == "BoxMesh"
    assert item.structured_content["name"] == "Wall"


async def test_mesh_library_target_and_mesh_source_are_exclusive() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        both_targets = await client.call_tool(
            "add_mesh_library_item",
            {"node_path": "Grid", "library_path": "res://l.tres", "mesh_type": "BoxMesh"},
            raise_on_error=False,
        )
        both_meshes = await client.call_tool(
            "add_mesh_library_item",
            {"node_path": "Grid", "mesh_type": "BoxMesh", "mesh_path": "res://m.tres"},
            raise_on_error=False,
        )
        neither_target = await client.call_tool(
            "create_mesh_library", {}, raise_on_error=False
        )
    assert both_targets.is_error and "only one" in str(both_targets.content)
    assert both_meshes.is_error
    assert neither_target.is_error
    assert "cmd_add_mesh_library_item" not in _commands(conn)


async def test_mesh_library_save_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        dry = await client.call_tool(
            "create_mesh_library", {"save_path": "res://blocks.tres", "dry_run": True}
        )
    assert dry.structured_content["dry_run"] is True
    assert "cmd_create_mesh_library" not in _commands(conn)


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        result = await client.call_tool(
            "add_mesh_instance", {"parent_path": ".", "mesh_type": "BoxMesh", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_add_mesh_instance" not in _commands(conn)


async def test_gridmap_get_cell_reads_cell() -> None:
    # #219 G5: read a GridMap cell (item + orientation) — inverts gridmap_set_cell.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scene_3d"})
        filled = await client.call_tool(
            "gridmap_get_cell", {"node_path": "GridMap", "position": [1, 0, 2]}
        )
        empty = await client.call_tool(
            "gridmap_get_cell", {"node_path": "GridMap", "position": [9, 9, 9]}
        )
        tools = {t.name: t for t in await client.list_tools()}
    f = filled.structured_content
    assert f["position"] == [1, 0, 2] and f["item"] == 3 and f["orientation"] == 22
    assert f["empty"] is False
    assert empty.structured_content["item"] == -1 and empty.structured_content["empty"] is True
    assert tools["gridmap_get_cell"].meta["safety_class"] == "read_only"
    assert "cmd_gridmap_get_cell" in _commands(conn)
