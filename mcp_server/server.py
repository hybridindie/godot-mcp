"""FastMCP server factory (issue #4).

Builds the AI-facing MCP server: wires the Godot bridge, registers tools, and
manages the bridge lifecycle via the server lifespan. The server is
transport-agnostic — ``main.py`` chooses stdio (default) or Streamable HTTP.

No I/O happens at import time; the bridge connects on startup (best-effort, so a
missing editor never blocks the server) and closes on shutdown
(see .opencode/rules/async-patterns.md).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import fastmcp_tasks  # noqa: F401  — importing enables Client-side task support (issue #315)
from fastmcp import FastMCP
from fastmcp_tasks import TasksExtension

from mcp_server.approval_middleware import ApprovalMiddleware
from mcp_server.bridge import Bridge
from mcp_server.capabilities import STATIC_CAPABILITY, apply_capability
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
from mcp_server.tools.undo import register_undo
from mcp_server.tools.visual_shader import register_visual_shader
from mcp_server.toolset_middleware import ToolsetMiddleware
from mcp_server.toolset_protocol import SERVER_INSTRUCTIONS
from mcp_server.toolsets import ToolsetManager, register_toolset_tools
from mcp_server.transforms import godot_tool_transform


async def register_tool_transform(mcp: FastMCP) -> None:
    """Register the ``godot_`` naming transform on the server.

    Normally called inside the server lifespan. Tests that need the transform
    without running the lifespan can call this directly.
    """
    mcp.add_transform(await godot_tool_transform(mcp))

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
    # Centralized at the tools/call boundary via ApprovalMiddleware (issue #330) so
    # the ``approval`` parameter no longer threads through register modules.
    approval = approval or ApprovalGate.from_config(config)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        # Start the bridge listener; the Godot addon connects (and reconnects) to it
        # (#276). Best-effort: if the port can't be bound (another server owns it), boot
        # anyway and report disconnected via health_check rather than failing — but log
        # it so the conflict is diagnosable.
        try:
            await bridge.serve()
            logger.info("bridge listening for the editor", extra={"url": config.bridge.url})
        except OSError:
            logger.warning(
                "bridge could not bind %s (another server may own it); continuing",
                config.bridge.url,
                exc_info=True,
            )
        try:
            await apply_safety_annotations(mcp)
        except Exception:
            logger.warning("failed to apply safety annotations", exc_info=True)
        try:
            mcp.add_transform(await godot_tool_transform(mcp))
        except Exception:
            logger.warning("failed to register tool transform", exc_info=True)
        try:
            yield
        finally:
            await bridge.close()

    # HTTP transport auth (issue #226): a StaticTokenVerifier gates the server
    # when a token is configured. Loopback without a token is allowed (validated
    # in main.py); non-loopback requires a token or main.py refuses to start.
    auth = None
    if config.auth_token:
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

        auth = StaticTokenVerifier(
            tokens={config.auth_token: {"client_id": "godot-mcp-client"}},
        )

    mcp = FastMCP(
        SERVER_NAME,
        lifespan=lifespan,
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://github.com/hybridindie/godot-mcp",
        auth=auth,
        # The dynamic fields (toolset_count / prompts / resources) are filled in
        # from the live registry after registration; see capabilities.apply_capability.
        experimental_capabilities={"godot_mcp": dict(STATIC_CAPABILITY)},
    )
    # Centralize the webhook ApprovalGate at the tools/call boundary (issue #330).
    # No-op unless a webhook is configured; dry_run short-circuits in the middleware.
    mcp.add_middleware(ApprovalMiddleware(approval))
    # Background tasks (issue #315): register the in-process TasksExtension so
    # tools marked ``task=True`` can return a handle immediately instead of
    # holding the MCP request open for the whole bridge op. Three long-running
    # tools are task-enabled (run_and_capture, export_project, bake_navigation_mesh);
    # their ctx.info/ctx.report_progress calls use safe_info/safe_progress
    # (tools/_progress.py) to no-op in the detached task session.
    mcp.add_extension(TasksExtension())

    register_health(mcp, bridge, config)
    register_undo(mcp, bridge)
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
    register_visual_shader(mcp, bridge)
    register_editor(mcp, bridge)
    resource_uris = register_resources(mcp, bridge)
    register_runtime(mcp, bridge, config, runner)
    register_runtime_session(mcp, bridge)
    register_runtime_inspect(mcp, bridge)
    register_import_asset(mcp, bridge)
    register_input_sim(mcp, bridge)
    register_input_map(mcp, bridge)
    register_testing(mcp, bridge, config, runner)
    register_profiling(mcp, bridge)
    register_batch(mcp, bridge)
    register_composite(mcp, bridge)
    register_debugger(mcp, bridge)
    register_analysis(mcp, bridge, config)
    register_export(mcp, bridge, config, runner)
    register_scripts(mcp, bridge, config, runner)
    register_debug_workflow(mcp, bridge, config, runner)
    register_project_scaffold(mcp, bridge)
    register_safety_tools(mcp)

    # Per-session toolset gating (issue #227): each client session has its own
    # enabled-set so one client enabling a toolset doesn't expose it to another.
    toolset_mw = ToolsetMiddleware()
    mcp.add_middleware(toolset_mw)

    # Gate the tool surface by category (per-session via the middleware above).
    manager = ToolsetManager(mcp, bridge=bridge, middleware=toolset_mw)
    register_toolset_tools(mcp, manager)

    # Comprehensive diagnostics: toolset counts, bridge state, troubleshooting.
    register_diagnostics(mcp, bridge, config, manager)

    # Register workflow prompts (instruction templates for the agent).
    prompt_names = register_prompts(mcp, bridge)

    # Derive standard MCP annotations (readOnlyHint/destructiveHint/...) from each
    # tool's safety_class, for every tool incl. gated-off ones (issue #220).
    # Applied inside the async lifespan (see above) since FastMCP 4.0's
    # local_provider.list_tools() is async.

    # Expose every tool as godot_<toolset>_<action> (issue #312). FastMCP 4.0's
    # ToolTransform renames tools as they flow to clients and reverse-maps public
    # names to the original handler on call_tool. Registered inside the async
    # lifespan (see above) so the public list_tools() API is available.

    # Fill the capabilities snapshot from the live registry so it can never drift
    # from the real toolset / prompt / resource catalog (issue #231/#233).
    apply_capability(mcp, manager, prompt_names, resource_uris)

    return mcp
