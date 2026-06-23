"""Static analysis tools (issue #49, #111).

Project-wide static analysis computed Python-side from the project's files (no addon
commands): unused resources, signal flow, circular script dependencies, scene-complexity
stats, asset dependencies, orphaned resources, scene integrity, and cross-scene
reference search. Gated `analysis` toolset; all `read_only`.

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
    AnalyzeDependenciesResult,
    CircularDependenciesResult,
    CrossSceneRefsResult,
    FindOrphanedResult,
    ProjectStatsResult,
    ProjectStructureResult,
    SignalFlowResult,
    UnusedResourcesResult,
    ValidateSceneIntegrityResult,
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

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def project_structure() -> ProjectStructureResult:
        """The project's raw inventory: all scene, script, and resource ``res://`` paths
        (sorted, non-overlapping buckets) plus ``entry_points`` (main scene, autoloads,
        plugins). Use it to learn what exists before planning edits — unlike
        ``project_stats`` (counts only), this returns the actual paths.
        """
        return ProjectStructureResult(**analysis.project_structure(await _index()))

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def analyze_dependencies(resource_path: str) -> AnalyzeDependenciesResult:
        """Parse a resource file and extract all ``res://`` / ``uid://`` references.
        Recurse into sub-dependencies (depth-limited). Returns the resource's inferred
        type, its direct/indirect references, and which project files refer to it.
        """
        return AnalyzeDependenciesResult(
            **analysis.analyze_dependencies(await _index(), resource_path)
        )

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def find_orphaned_resources(
        scan_dir: str = "res://", resource_types: list[str] | None = None
    ) -> FindOrphanedResult:
        """Find resource files not referenced by any project file, excluding entry points
        and the ``.godot/`` cache. Optionally filter by Godot type (e.g. ``["Texture2D"]``).
        """
        return FindOrphanedResult(
            **analysis.find_orphaned_resources(await _index(), scan_dir, resource_types)
        )

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def validate_scene_integrity(scene_path: str) -> ValidateSceneIntegrityResult:
        """Check a scene file for broken ``ext_resource`` paths, missing
        scripts, and broken signal connections. Returns errors (blocking) and warnings
        (non-blocking). ``valid`` is true only when there are zero errors.
        """
        return ValidateSceneIntegrityResult(
            **analysis.validate_scene_integrity(await _index(), scene_path)
        )

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def cross_scene_find_refs(target_path: str) -> CrossSceneRefsResult:
        """Scan all project files for references to ``target_path``. Returns which
        scenes, resources, and scripts mention it.
        """
        return CrossSceneRefsResult(**analysis.cross_scene_find_refs(await _index(), target_path))

