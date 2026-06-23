"""Contract tests for particle tools (issue #42)."""

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
        case "cmd_create_particles":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "particles_type": p["particles_type"],
                    "created": True,
                },
            )
        case "cmd_set_particle_material":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "properties": p["properties"]}
            )
        case "cmd_set_particle_color_gradient":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "stops": len(p["colors"])}
            )
        case "cmd_apply_particle_preset":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "preset": p["preset"]}
            )
        case "cmd_get_particle_material":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "has_material": True,
                    "properties": {"gravity": {"x": 0.0, "y": -98.0, "z": 0.0}, "spread": 45.0},
                    "color_ramp": {
                        "colors": [
                            {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
                            {"r": 1.0, "g": 0.0, "b": 0.0, "a": 0.0},
                        ],
                        "offsets": [0.0, 1.0],
                    },
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_particles_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_particles_create" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "particles"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_particles_create",
        "godot_particles_set_material",
        "godot_particles_set_color_gradient",
        "godot_particles_apply_preset",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_create_and_configure_material() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "particles"})
        created = await client.call_tool(
            "godot_particles_create",
            {"parent_path": ".", "particles_type": "GPUParticles3D", "amount": 64},
        )
        mat = await client.call_tool(
            "godot_particles_set_material",
            {"node_path": "GPUParticles3D", "properties": {"spread": 30.0}},
        )
    assert created.structured_content["particles_type"] == "GPUParticles3D"
    assert created.structured_content["node_path"] == "./GPUParticles3D"
    assert mat.structured_content["properties"]["spread"] == 30.0


async def test_color_gradient_and_preset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "particles"})
        grad = await client.call_tool(
            "godot_particles_set_color_gradient",
            {"node_path": "GPUParticles2D", "colors": ["#ffee88", "#ff6600", "#00000000"]},
        )
        preset = await client.call_tool(
            "godot_particles_apply_preset", {"node_path": "GPUParticles2D", "preset": "fire"}
        )
    assert grad.structured_content["stops"] == 3
    assert preset.structured_content["preset"] == "fire"


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "particles"})
        result = await client.call_tool(
            "godot_particles_apply_preset",
            {"node_path": "GPUParticles2D", "preset": "smoke", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_apply_particle_preset" not in _commands(conn)


async def test_get_particle_material_reads_props_and_ramp() -> None:
    # #219 P4: read the process_material props + color ramp — inverts the writers.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "particles"})
        result = await client.call_tool(
            "godot_particles_get_material", {"node_path": "GPUParticles2D"}
        )
        tools = {t.name: t for t in await client.list_tools()}
    data = result.structured_content
    assert data["has_material"] is True
    assert data["properties"]["spread"] == 45.0
    assert data["properties"]["gravity"] == {"x": 0.0, "y": -98.0, "z": 0.0}
    assert data["color_ramp"]["offsets"] == [0.0, 1.0]
    assert data["color_ramp"]["colors"][0] == {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    assert tools["godot_particles_get_material"].meta["safety_class"] == "read_only"
    cmds = [CommandEnvelope.model_validate_json(s).command for s in conn.sent]
    assert "cmd_get_particle_material" in cmds
