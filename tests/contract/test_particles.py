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
        assert "create_particles" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "particles"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "create_particles",
        "set_particle_material",
        "set_particle_color_gradient",
        "apply_particle_preset",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_create_and_configure_material() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "particles"})
        created = await client.call_tool(
            "create_particles",
            {"parent_path": ".", "particles_type": "GPUParticles3D", "amount": 64},
        )
        mat = await client.call_tool(
            "set_particle_material",
            {"node_path": "GPUParticles3D", "properties": {"spread": 30.0}},
        )
    assert created.structured_content["particles_type"] == "GPUParticles3D"
    assert created.structured_content["node_path"] == "./GPUParticles3D"
    assert mat.structured_content["properties"]["spread"] == 30.0


async def test_color_gradient_and_preset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "particles"})
        grad = await client.call_tool(
            "set_particle_color_gradient",
            {"node_path": "GPUParticles2D", "colors": ["#ffee88", "#ff6600", "#00000000"]},
        )
        preset = await client.call_tool(
            "apply_particle_preset", {"node_path": "GPUParticles2D", "preset": "fire"}
        )
    assert grad.structured_content["stops"] == 3
    assert preset.structured_content["preset"] == "fire"


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "particles"})
        result = await client.call_tool(
            "apply_particle_preset",
            {"node_path": "GPUParticles2D", "preset": "smoke", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_apply_particle_preset" not in _commands(conn)
