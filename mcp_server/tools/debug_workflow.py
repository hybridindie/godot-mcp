"""Debug workflow tool: thin delegator to the debug-workflow service.

Aggregates several read-only diagnostics into one call. All logic lives in
``mcp_server.debug_workflow`` (per .claude/rules/architecture.md — tool bodies
are delegation only); this module just registers and wires the tool.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.constraints import TimeoutSeconds
from mcp_server.debug_workflow import run_debug_workflow
from mcp_server.models.debug_workflow import DebugWorkflowResult
from mcp_server.runtime import Runner
from mcp_server.safety import READ_ONLY


def register_debug_workflow(
    mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner
) -> None:
    """Register the debug_workflow aggregator tool."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def debug_workflow(
        scene: str = "",
        timeout_seconds: TimeoutSeconds = 5.0,
    ) -> DebugWorkflowResult:
        """Run a comprehensive debug check on the project and return a unified report.

        This aggregates multiple diagnostics into one call so you (or the LLM) can
        spot problems quickly without calling each tool individually.

        Checks performed:
        1. Parse errors across all GDScript files
        2. Active scene tree structure (nodes, scripts, properties)
        3. Headless run of the project (or a specific scene) capturing errors/warnings
        4. Bridge connection state and Godot version

        ``scene`` — optional res:// path to focus the headless run on a specific scene.
        """
        return await run_debug_workflow(bridge, config, runner, scene, timeout_seconds)
