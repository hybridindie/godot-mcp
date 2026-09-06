"""Shared parametrized test for the dry_run safety invariant.

Table-driven: one row per domain, replacing the identical
``test_dry_run_sends_no_mutation`` copy that each domain's contract file
used to carry.  Domain-specific tests (preview shapes, data assertions,
per-toolset safety-class splits) stay in their respective files.
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


def _shared_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    """Minimal responder handling the preconditions shared across domains.

    Unknown commands get a ``VALIDATION_ERROR`` rather than ``None``: that is
    what lets :class:`FakeAddonConnection` swap in its own answer for the
    bootstrap commands (``cmd_ping``, ``cmd_get_project_info``), which it only
    does for a non-``None`` ``VALIDATION_ERROR`` response.
    """
    match cmd.command:
        case "cmd_node_exists":
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://m.tscn"})
        case _:
            return ResponseEnvelope.failure(
                cmd.id, "VALIDATION_ERROR", f"Unknown command '{cmd.command}'."
            )


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_shared_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


# ---------------------------------------------------------------------------
# dry_run sends no mutation
# ---------------------------------------------------------------------------

DRY_RUN_CASES = [
    pytest.param(
        "animation",
        "godot_animation_create",
        {"node_path": "AnimationPlayer", "name": "walk"},
        "cmd_create_animation",
        id="animation-create",
    ),
    pytest.param(
        "audio",
        "godot_audio_add_bus",
        {"name": "SFX"},
        "cmd_add_audio_bus",
        id="audio-add-bus",
    ),
    pytest.param(
        "navigation",
        "godot_navigation_bake_mesh",
        {"node_path": "NavigationRegion3D"},
        "cmd_bake_navigation_mesh",
        id="navigation-bake-mesh",
    ),
    pytest.param(
        "scene_edit",
        "godot_scene_edit_duplicate_node",
        {"node_path": "Box"},
        "cmd_duplicate_node",
        id="scene_edit-duplicate-node",
    ),
    pytest.param(
        "particles",
        "godot_particles_apply_preset",
        {"node_path": "GPUParticles2D", "preset": "smoke"},
        "cmd_apply_particle_preset",
        id="particles-apply-preset",
    ),
    pytest.param(
        "physics",
        "godot_physics_set_layers",
        {"node_path": "Body", "layers": [1]},
        "cmd_set_physics_layers",
        id="physics-set-layers",
    ),
    pytest.param(
        "scene_3d",
        "godot_scene_3d_add_mesh_instance",
        {"parent_path": ".", "mesh_type": "BoxMesh"},
        "cmd_add_mesh_instance",
        id="scene_3d-add-mesh",
    ),
    pytest.param(
        "shader",
        "godot_shader_create",
        {"shader_path": "res://fx.gdshader"},
        "cmd_create_shader",
        id="shader-create",
    ),
    pytest.param(
        "theme_ui",
        "godot_theme_ui_set_color",
        {"node_path": "UI", "name": "font_color", "color": "#ffffff"},
        "cmd_set_theme_color",
        id="theme_ui-set-color",
    ),
]


@pytest.mark.parametrize(
    "category,tool_name,tool_args,expected_command",
    DRY_RUN_CASES,
)
async def test_dry_run_sends_no_mutation(
    category: str,
    tool_name: str,
    tool_args: dict[str, object],
    expected_command: str,
) -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": category})
        result = await client.call_tool(tool_name, {**tool_args, "dry_run": True})
    assert result.structured_content["dry_run"] is True
    assert expected_command not in _commands(conn)
