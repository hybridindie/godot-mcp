"""Profiling tools (issue #38).

Read Godot's ``Performance`` monitors (FPS, frame/physics time, memory, object/node
counts, draw calls, video memory, physics actives) for the editor or a *running* game.
Gated `profiling` toolset; both `read_only`. The running-game reading uses the #66
runtime probe (live monitors are most meaningful during a play session).
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PROFILING_TAG
from mcp_server.constraints import TimeoutMs
from mcp_server.defaults import (
    DEFAULT_PERF_MONITORS_TIMEOUT_MS,
)
from mcp_server.models.profiling import EditorPerformanceResult, GamePerformanceResult
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import poll_ready, route

PROFILING = {PROFILING_TAG}


def register_profiling(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the profiling tools."""

    @mcp.tool(meta=READ_ONLY, tags=PROFILING)
    async def get_editor_performance() -> EditorPerformanceResult:
        """Read the editor process's Performance monitors (fps, process_time, memory_static,
        object/node counts, draw_calls, video_mem_used, …) as a name→value map.

        WHEN TO USE: You suspect the editor itself is slow (laggy UI, slow scene
        loading) and want to check editor-side metrics before blaming the game.
        WHEN NOT TO USE: You need to measure the running game's performance —
        use get_performance_monitors() to read the live game process instead.
        """
        return EditorPerformanceResult(**await route(bridge, "cmd_get_editor_performance", {}))

    @mcp.tool(meta=READ_ONLY, tags=PROFILING)
    async def get_performance_monitors(
        timeout_ms: TimeoutMs = DEFAULT_PERF_MONITORS_TIMEOUT_MS,
    ) -> GamePerformanceResult:
        """Read the *running* game's Performance monitors (same metrics, live) via the
        runtime probe. Requires a play session; if the probe isn't connected, returns
        ``connected=false`` with a hint. Errors (no play session) surface structured.

        WHEN TO USE: The game is running and you want live FPS, memory usage, or
        draw calls during gameplay (e.g., after simulating input to trigger a
        particle effect and checking frame time).
        WHEN NOT TO USE: The game is NOT running and you want to check the editor's
        own performance — use get_editor_performance() instead.
        """
        result = await poll_ready(bridge, "cmd_get_performance_monitors", {}, timeout_ms)
        return GamePerformanceResult(**result)
