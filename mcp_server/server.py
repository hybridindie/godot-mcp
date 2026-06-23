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
from mcp_server.safety import ApprovalGate, apply_safety_annotations, register_safety_tools
from mcp_server.tools.analysis import register_analysis
from mcp_server.tools.animation import register_animation
from mcp_server.tools.audio import register_audio
from mcp_server.tools.batch import register_batch
from mcp_server.tools.composite import register_composite
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
from mcp_server.tools.project_scaffold import register_project_scaffold
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
from mcp_server.tools.visual_shader import register_visual_shader
from mcp_server.toolset_protocol import SERVER_INSTRUCTIONS
from mcp_server.toolsets import ToolsetManager, register_toolset_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "godot-mcp"


def create_server(
    config: ServerConfig | None = None,
    bridge: Bridge | None = None,
    runner: Runner | None = None,
    approval: ApprovalGate | None = None,
) -> FastMCP:
    """Create the FastMCP server, wiring the bridge and registering tools."""
    config = config or ServerConfig()
    bridge = bridge or Bridge(config.bridge)
    runner = runner or GodotRunner(config)
    # Human-in-the-loop approval gate (issue #153); no-op unless a webhook is set.
    approval = approval or ApprovalGate.from_config(config)

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
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://github.com/hybridindie/godot-mcp",
        # The dynamic fields (toolset_count / prompts / resources) are filled in
        # from the live registry after registration; see _apply_capabilities below.
        experimental_capabilities={
            "godot_mcp": {
                "version": "2026.06.01",
                "min_godot": "4.4",
                "docs": {
                    "tutorial": "https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md",
                    "tool_contracts": "https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md",
                    "architecture": "https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md",
                },
            }
        },
    )
    register_health(mcp, bridge, config)
    register_inspection(mcp, bridge)
    register_mutation(mcp, bridge, approval)
    register_scene_session(mcp, bridge, approval)
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
    register_visual_shader(mcp, bridge)
    register_editor(mcp, bridge)
    resource_uris = register_resources(mcp, bridge)
    register_runtime(mcp, bridge, config, runner)
    register_runtime_session(mcp, bridge)
    register_runtime_inspect(mcp, bridge)
    register_import_asset(mcp, bridge)
    register_input_sim(mcp, bridge)
    register_input_map(mcp, bridge, approval)
    register_testing(mcp, bridge, config, runner)
    register_profiling(mcp, bridge)
    register_batch(mcp, bridge)
    register_composite(mcp, bridge)
    register_debugger(mcp, bridge)
    register_analysis(mcp, bridge, config)
    register_export(mcp, bridge, config, runner)
    register_scripts(mcp, bridge, config, runner)
    register_debug_workflow(mcp, bridge, config, runner)
    register_project_scaffold(mcp, bridge, approval)
    register_safety_tools(mcp)

    # Gate the tool surface by category, then apply the default exposure (core +
    # inspection on; scene_edit and future categories off until enabled).
    manager = ToolsetManager(mcp, bridge=bridge)
    register_toolset_tools(mcp, manager)
    manager.apply_defaults()

    # Comprehensive diagnostics: toolset counts, bridge state, troubleshooting.
    register_diagnostics(mcp, bridge, config, manager)

    # Register workflow prompts (instruction templates for the agent).
    prompt_names = register_prompts(mcp)

    # Derive standard MCP annotations (readOnlyHint/destructiveHint/...) from each
    # tool's safety_class, for every tool incl. gated-off ones (issue #220).
    apply_safety_annotations(mcp)

    # Fill the capabilities snapshot from the live registry so it can never drift
    # from the real toolset / prompt / resource catalog (issue #231).
    _apply_capabilities(mcp, manager, prompt_names, resource_uris)

    return mcp


def _apply_capabilities(
    mcp: FastMCP, manager: ToolsetManager, prompts: list[str], resources: list[str]
) -> None:
    """Derive the dynamic ``experimental_capabilities`` fields from the live registry.

    ``toolset_count`` comes from ``manager.status()`` (the gated toolsets plus the
    always-on ``core`` toolset — everything ``list_toolsets`` reports); ``prompts``
    and ``resources`` are the names the registration functions report, so the
    snapshot tracks the catalog without introspecting FastMCP internals (#231/#233).
    """
    caps = mcp.experimental_capabilities["godot_mcp"]
    caps["toolset_count"] = len(manager.status())
    caps["prompts"] = prompts
    caps["resources"] = resources
