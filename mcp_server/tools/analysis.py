"""Static analysis tools (issue #49).

Project-wide static analysis computed Python-side from the project's files (no addon
commands): unused resources, signal flow, circular script dependencies, and
scene-complexity stats. Gated `analysis` toolset; all `read_only`.

The project directory is resolved like the runtime loop (#13): ``GODOT_MCP_PROJECT_DIR``
else the connected editor's project. Results are heuristic (text analysis), so
dynamically-built resource paths aren't tracked.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import FastMCP

from mcp_server import analysis
from mcp_server.bridge import Bridge
from mcp_server.categories import ANALYSIS_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.analysis import (
    CircularDependenciesResult,
    ProjectStatsResult,
    SignalFlowResult,
    UnusedResourcesResult,
)
from mcp_server.runtime import resolve_project_dir
from mcp_server.safety import READ_ONLY, PreconditionError, enforce_preconditions

ANALYSIS = {ANALYSIS_TAG}


def register_analysis(mcp: FastMCP, bridge: Bridge, config: ServerConfig) -> None:
    """Register the static analysis tools."""

    async def _index() -> analysis.ProjectIndex:
        project_dir = Path(await resolve_project_dir(bridge, config))
        if not project_dir.is_dir():
            raise PreconditionError(
                f"Project directory '{project_dir}' is not accessible from the server.",
                required="project_dir",
            )
        # The scan is synchronous file I/O; run it off the event loop.
        return await asyncio.to_thread(analysis.scan, project_dir)

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def find_unused_resources() -> UnusedResourcesResult:
        """Find resource files not referenced by any project file (and not an entry point
        like the main scene or an autoload). Heuristic: dynamically-loaded or
        externally-referenced resources may show as false positives.
        """
        return UnusedResourcesResult(**analysis.find_unused_resources(await _index()))

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def analyze_signal_flow(scene: str = "") -> SignalFlowResult:
        """Map signal connections declared in scene files (``[connection ...]``): each
        ``{scene, signal, from, to, method}``. Limit to one ``scene`` (a ``res://*.tscn``)
        or omit for the whole project.
        """
        return SignalFlowResult(**analysis.analyze_signal_flow(await _index(), scene))

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def detect_circular_dependencies() -> CircularDependenciesResult:
        """Detect cycles in the script dependency graph (``preload``/``load``/``extends``
        among project ``.gd`` files). Each cycle is an ordered list of script paths.
        """
        return CircularDependenciesResult(**analysis.detect_circular_dependencies(await _index()))

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def project_stats() -> ProjectStatsResult:
        """Project complexity stats: scene/script/resource counts, total nodes, signal
        connections, a per-extension breakdown, and the busiest scenes by node count.
        """
        return ProjectStatsResult(**analysis.project_stats(await _index()))
