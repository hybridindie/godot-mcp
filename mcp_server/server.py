"""FastMCP server factory (issue #4).

Builds the AI-facing MCP server: wires the Godot bridge, registers tools, and
manages the bridge lifecycle via the server lifespan. The server is
transport-agnostic — ``main.py`` chooses stdio (default) or Streamable HTTP.

No I/O happens at import time; the bridge connects on startup (best-effort, so a
missing editor never blocks the server) and closes on shutdown
(see .claude/rules/async-patterns.md).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.diagnostics import register_diagnostics
from mcp_server.prompts import register_prompts
from mcp_server.resources.context import register_resources
from mcp_server.runtime import GodotRunner, Runner
from mcp_server.safety import register_safety_tools
from mcp_server.tools.analysis import register_analysis
from mcp_server.tools.animation import register_animation
from mcp_server.tools.audio import register_audio
from mcp_server.tools.batch import register_batch
from mcp_server.tools.debug_workflow import register_debug_workflow
from mcp_server.tools.debugger import register_debugger
from mcp_server.tools.editor import register_editor
from mcp_server.tools.export import register_export
from mcp_server.tools.health import register_health
from mcp_server.tools.import_asset import register_import_asset
from mcp_server.tools.input_map import register_input_map
from mcp_server.tools.input_sim import register_input_sim
from mcp_server.tools.inspection import register_inspection
from mcp_server.tools.mutation import register_mutation
from mcp_server.tools.navigation import register_navigation
from mcp_server.tools.node_ops import register_node_ops
from mcp_server.tools.particles import register_particles
from mcp_server.tools.physics import register_physics
from mcp_server.tools.profiling import register_profiling
from mcp_server.tools.project_fs import register_project_fs
from mcp_server.tools.resource_files import register_resource_files
from mcp_server.tools.runtime import register_runtime
from mcp_server.tools.runtime_inspect import register_runtime_inspect
from mcp_server.tools.runtime_session import register_runtime_session
from mcp_server.tools.scene_3d import register_scene_3d
from mcp_server.tools.scene_session import register_scene_session
from mcp_server.tools.scripts import register_scripts
from mcp_server.tools.shader import register_shader
from mcp_server.tools.testing import register_testing
from mcp_server.tools.theme_ui import register_theme_ui
from mcp_server.tools.tilemap import register_tilemap
from mcp_server.toolsets import ToolsetManager, register_toolset_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "godot-mcp"


def create_server(
    config: ServerConfig | None = None,
    bridge: Bridge | None = None,
    runner: Runner | None = None,
) -> FastMCP:
    """Create the FastMCP server, wiring the bridge and registering tools."""
    config = config or ServerConfig()
    bridge = bridge or Bridge(config.bridge)
    runner = runner or GodotRunner(config)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        # Best-effort connect: if Godot isn't running, start anyway and report
        # disconnected via health_check rather than failing to boot — but log the
        # failure so a wrong URL / missing addon is diagnosable.
        try:
            await bridge.connect()
            logger.info("bridge connected", extra={"url": config.bridge.url})
        except Exception:
            logger.warning(
                "bridge not connected at startup; continuing (check the editor/addon)",
                extra={"url": config.bridge.url},
                exc_info=True,
            )
        try:
            yield
        finally:
            await bridge.close()

    mcp = FastMCP(
        SERVER_NAME,
        lifespan=lifespan,
        instructions=(
            "You are connected to a godot-mcp server that gates its tools into categories "
            "called 'toolsets'. Only 'core' (diagnostics, toolset management) and "
            "'inspection' (read-only project/scene/node reading) are enabled by default. "
            "Every other capability is hidden until you explicitly enable it.\n\n"
            "MANDATORY PROTOCOL:\n"
            "1. Call get_server_info() for a full capability snapshot "
            "(toolsets, bridge state, troubleshooting).\n"
            "2. Call list_toolsets() to see what is available and which are enabled.\n"
            "3. Call enable_toolset(category) for every category you plan to use.\n"
            "4. Only after enabling can you call the tools in that category.\n\n"
            "Common toolsets you will need:\n"
            "- scene_edit  → create_node, set_node_property, attach_script, save_scene\n"
            "- scripts     → write_script, read_script, get_parse_errors\n"
            "- runtime     → run_and_capture (headless), play_scene (editor)\n"
            "- input       → simulate_action, simulate_key, play_input_sequence\n"
            "- testing     → assert_node_state, run_test_scenario\n"
            "- batch       → batch_set_property, find_nodes_by_type\n"
            "- physics     → setup_physics_body, setup_collision\n"
            "- resources_edit → register_autoload, create_resource\n"
            "- asset_import → import_asset, create_material_from_textures\n\n"
            "DOCUMENTATION:\n"
            "- Tutorial (prompt-driven walkthrough): https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md\n"
            "- Tool contracts (per-tool spec): https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md\n"
            "- Architecture (bridge contract): https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md\n\n"
            "If you try to call a tool and get 'ToolError: unknown tool', the toolset "
            "is not enabled. Call enable_toolset first.\n\n"
            "This server exposes workflow prompts (toolset_discovery, build_scene, "
            "play_test, script_edit, debug_scene, troubleshoot) and a diagnostics tool "
            "(get_server_info) that returns tool counts, bridge state, active scene, "
            "and common errors with fixes."
        ),
        website_url="https://github.com/hybridindie/godot-mcp",
        experimental_capabilities={
            "godot_mcp": {
                "version": "2026.06.01",
                "min_godot": "4.4",
                "toolset_count": 26,
                "docs": {
                    "tutorial": "https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md",
                    "tool_contracts": "https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md",
                    "architecture": "https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md",
                },
                "prompts": [
                    "toolset_discovery",
                    "build_scene",
                    "play_test",
                    "script_edit",
                    "debug_scene",
                    "troubleshoot",
                ],
                "resources": [
                    "godot://project/info",
                    "godot://scene/current",
                    "godot://scene/tree",
                    "godot://scene/tree/{max_depth}",
                    "godot://node/selected",
                ],
            }
        },
    )
    register_health(mcp, bridge, config)
    register_inspection(mcp, bridge)
    register_mutation(mcp, bridge)
    register_scene_session(mcp, bridge)
    register_node_ops(mcp, bridge)
    register_resource_files(mcp, bridge)
    register_project_fs(mcp, bridge)
    register_physics(mcp, bridge)
    register_animation(mcp, bridge)
    register_scene_3d(mcp, bridge)
    register_particles(mcp, bridge)
    register_navigation(mcp, bridge)
    register_audio(mcp, bridge)
    register_tilemap(mcp, bridge)
    register_theme_ui(mcp, bridge)
    register_shader(mcp, bridge)
    register_editor(mcp, bridge)
    register_resources(mcp, bridge)
    register_runtime(mcp, bridge, config, runner)
    register_runtime_session(mcp, bridge)
    register_runtime_inspect(mcp, bridge)
    register_import_asset(mcp, bridge)
    register_input_sim(mcp, bridge)
    register_input_map(mcp, bridge)
    register_testing(mcp, bridge)
    register_profiling(mcp, bridge)
    register_batch(mcp, bridge)
    register_debugger(mcp, bridge)
    register_analysis(mcp, bridge, config)
    register_export(mcp, bridge, config, runner)
    register_scripts(mcp, bridge, config, runner)
    register_debug_workflow(mcp, bridge, config, runner)
    register_safety_tools(mcp)

    # Gate the tool surface by category, then apply the default exposure (core +
    # inspection on; scene_edit and future categories off until enabled).
    manager = ToolsetManager(mcp, bridge=bridge)
    register_toolset_tools(mcp, manager)
    manager.apply_defaults()

    # Comprehensive diagnostics: toolset counts, bridge state, troubleshooting.
    register_diagnostics(mcp, bridge, config, manager)

    # Register workflow prompts (instruction templates for the agent).
    register_prompts(mcp)

    return mcp
