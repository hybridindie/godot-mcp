"""Read-only inspection tools (issue #5).

The most frequently called tools: they let an agent understand the project and
scene before making changes. All ``read_only`` — they never mutate anything.
Each is a thin wrapper that routes to the addon and returns a typed model.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.models.inspection import (
    ActiveScene,
    NodeInfo,
    ProjectInfo,
    SceneTree,
    SelectedNode,
)
from mcp_server.tools._route import route

READ_ONLY = {"safety_class": "read_only"}


def register_inspection(mcp: FastMCP, bridge: Bridge) -> None:
    """Register all five inspection tools on the server."""

    @mcp.tool(meta=READ_ONLY)
    async def get_project_info() -> ProjectInfo:
        """Get project-level context: name, Godot version, main scene, autoloads,
        and project-defined input actions. Call this to orient before editing.
        """
        return ProjectInfo(**await route(bridge, "cmd_get_project_info"))

    @mcp.tool(meta=READ_ONLY)
    async def get_active_scene() -> ActiveScene:
        """Get the currently open scene's path and name. Returns ``is_open=False``
        when no scene is open (not an error).
        """
        return ActiveScene(**await route(bridge, "cmd_get_active_scene"))

    @mcp.tool(meta=READ_ONLY)
    async def get_scene_tree(max_depth: int = -1) -> SceneTree:
        """Get the open scene as a recursive tree of {name, type, script, children}.

        ``max_depth`` limits how many child levels are returned (-1 = unlimited,
        0 = root only); use it to avoid huge payloads on deep scenes. ``tree`` is
        null when no scene is open.
        """
        return SceneTree(**await route(bridge, "cmd_get_scene_tree", {"max_depth": max_depth}))

    @mcp.tool(meta=READ_ONLY)
    async def get_selected_node() -> SelectedNode:
        """Get the node currently selected in the editor — its path, type, script,
        properties, and child names. Returns ``selected=None`` when nothing is
        selected.
        """
        return SelectedNode(**await route(bridge, "cmd_get_selected_node"))

    @mcp.tool(meta=READ_ONLY)
    async def get_node_properties(node_path: str) -> NodeInfo:
        """Get a node's detail by scene-relative path (e.g. "Player/Sprite2D"):
        type, attached script, exported/set properties, and child names. Errors
        with RESOURCE_NOT_FOUND if the path doesn't resolve, or PRECONDITION_FAILED
        if no scene is open.
        """
        return NodeInfo(**await route(bridge, "cmd_get_node_properties", {"node_path": node_path}))
