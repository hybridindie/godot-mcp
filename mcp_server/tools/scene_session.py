"""Scene session management tools (issue #79).

Editor session control: open/reload/save-all/list/select — all in the
``scene_edit`` toolset. ``reload_scene`` is ``destructive`` (discards unsaved
changes and needs ``confirm``); the rest are ``mutating`` or ``read_only``.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SCENE_EDIT_TAG
from mcp_server.models.scene_session import (
    ListOpenScenesResult,
    OpenSceneInfo,
    OpenSceneResult,
    ReloadSceneResult,
    SaveAllScenesResult,
    SelectNodesResult,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_confirmation,
    require_node_exists,
)
from mcp_server.tools._route import route, run_or_preview

SCENE_EDIT = {SCENE_EDIT_TAG}


def register_scene_session(mcp: FastMCP, bridge: Bridge) -> None:
    """Register scene session tools in the scene_edit toolset."""

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def open_scene(scene_path: str, dry_run: bool = False) -> OpenSceneResult:
        """Open an existing scene file for editing.

        If the scene is already open, returns ``already_open=True``.
        """
        require_bridge_connected(bridge)
        params: dict[str, Any] = {"scene_path": scene_path}
        preview = {"scene_path": scene_path, "opened": False, "already_open": False}
        return await run_or_preview(
            dry_run, OpenSceneResult, preview, bridge, "cmd_open_scene", params
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=SCENE_EDIT)
    @enforce_preconditions
    async def reload_scene(
        scene_path: str, confirm: bool = False, dry_run: bool = False
    ) -> ReloadSceneResult:
        """Reload the scene at ``scene_path`` from disk, discarding unsaved changes.

        Destructive: requires ``confirm=True``.
        """
        require_bridge_connected(bridge)
        if not dry_run:
            require_confirmation(confirm, "reload_scene")
        params: dict[str, Any] = {"scene_path": scene_path, "confirm": True}
        preview = {"scene_path": scene_path, "reloaded": False}
        return await run_or_preview(
            dry_run, ReloadSceneResult, preview, bridge, "cmd_reload_scene", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def save_all_scenes(dry_run: bool = False) -> SaveAllScenesResult:
        """Save all currently open scenes. Returns the count saved."""
        await require_active_scene(bridge)
        preview = {"saved": False, "count": 0}
        return await run_or_preview(
            dry_run, SaveAllScenesResult, preview, bridge, "cmd_save_all_scenes"
        )

    @mcp.tool(meta=READ_ONLY, tags=SCENE_EDIT)
    @enforce_preconditions
    async def list_open_scenes() -> ListOpenScenesResult:
        """List the currently open scenes with their modification status."""
        require_bridge_connected(bridge)
        raw = await route(bridge, "cmd_list_open_scenes")
        # Ensure the list is typed — allow the addon to omit "scenes".
        scenes = [
            OpenSceneInfo.model_validate(item) for item in raw.get("scenes", [])
        ]
        return ListOpenScenesResult(scenes=scenes)

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def select_nodes(
        node_paths: list[str], dry_run: bool = False
    ) -> SelectNodesResult:
        """Select the nodes at ``node_paths`` (scene-relative) in the editor.

        Replaces the current selection with the given nodes.
        """
        await require_active_scene(bridge)
        for path in node_paths:
            await require_node_exists(bridge, path)
        params: dict[str, Any] = {"node_paths": node_paths}
        preview = {"scene_path": "", "selected": node_paths, "count": len(node_paths)}
        return await run_or_preview(
            dry_run, SelectNodesResult, preview, bridge, "cmd_select_nodes", params
        )
