"""Batch / refactor tools (issue #48).

Operate over many nodes/scenes at once: find nodes by type, batch-set a property in the
open scene, apply a property change across scene *files*, and analyze dependencies. Gated
`batch` toolset. Finds/deps are `read_only`; the writes are `mutating` with `dry_run`.

Cross-scene edits touch files on disk (not the open editor copy): the currently-edited
scene is skipped (its in-memory copy would clobber the change — use batch_set_property
there), background/closed scenes are edited and re-scanned, and every target is reported
(modified count + any error), so skips are explicit.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import BATCH_TAG
from mcp_server.models.batch import (
    BatchSetResult,
    CrossSceneResult,
    DependenciesResult,
    FindNodesResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_active_scene
from mcp_server.tools._route import route

BATCH = {BATCH_TAG}


def register_batch(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the batch / refactor tools."""

    @mcp.tool(meta=READ_ONLY, tags=BATCH)
    async def find_nodes_by_type(
        node_type: str, parent_path: str = ".", recursive: bool = True
    ) -> FindNodesResult:
        """Find nodes in the open scene whose class is (or derives from) ``node_type``
        (e.g. "Sprite2D", "Control") under ``parent_path``. Returns each node's path,
        name, and concrete type — feed the paths into ``batch_set_property``.
        """
        params = {"type": node_type, "parent_path": parent_path, "recursive": recursive}
        return FindNodesResult(**await route(bridge, "cmd_find_nodes_by_type", params))

    @mcp.tool(meta=MUTATING, tags=BATCH)
    @enforce_preconditions
    async def batch_set_property(
        property: str,
        value: Any,
        node_paths: list[str] | None = None,
        node_type: str = "",
        dry_run: bool = False,
    ) -> BatchSetResult:
        """Set ``property`` to ``value`` on many nodes in the open scene, in one undoable
        action. Target by explicit ``node_paths`` or by ``node_type`` (all matching nodes).
        Nodes lacking the property are reported in ``skipped``. ``dry_run`` returns the plan
        (applied/skipped) without changing anything.
        """
        await require_active_scene(bridge)
        params: dict[str, Any] = {"property": property, "value": value, "dry_run": dry_run}
        if node_paths:
            params["node_paths"] = node_paths
        if node_type:
            params["type"] = node_type
        return BatchSetResult(**await route(bridge, "cmd_batch_set_property", params))

    @mcp.tool(meta=MUTATING, tags=BATCH)
    @enforce_preconditions
    async def cross_scene_set_property(
        scenes: list[str],
        node_type: str,
        property: str,
        value: Any,
        dry_run: bool = False,
    ) -> CrossSceneResult:
        """Set ``property`` to ``value`` on every ``node_type`` node across the given
        ``scenes`` (``res://*.tscn`` files), editing them on disk and re-scanning. The
        currently-edited scene is skipped (reported as an error). Each scene's result lists
        the ``modified`` count and any ``error``. ``dry_run`` reports counts without saving.
        """
        params = {
            "scenes": scenes,
            "type": node_type,
            "property": property,
            "value": value,
            "dry_run": dry_run,
        }
        return CrossSceneResult(**await route(bridge, "cmd_cross_scene_set_property", params))

    @mcp.tool(meta=READ_ONLY, tags=BATCH)
    async def get_dependencies(path: str) -> DependenciesResult:
        """List the resources the resource/scene at ``path`` (a ``res://`` file) depends on
        — each as ``{raw, path, type}``. Use it to understand impact before refactoring.
        """
        return DependenciesResult(**await route(bridge, "cmd_get_dependencies", {"path": path}))
