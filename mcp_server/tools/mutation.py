"""Scene mutation tools (issue #6).

The first set of editor *changes* an agent can make. Every tool:
- is tagged ``mutating`` (or ``destructive`` for delete),
- runs preconditions first (structured failures, never tracebacks),
- supports ``dry_run=True`` to preview without changing anything,
- routes to a UndoRedo-wrapped ``cmd_*`` addon handler.

All editor work + UndoRedo lives in the addon; all safety lives here
(see .claude/rules/architecture.md and safety.py).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SCENE_EDIT_TAG
from mcp_server.models.mutation import (
    AttachScriptResult,
    ConnectSignalResult,
    CreateNodeResult,
    CreateSceneResult,
    DeleteNodeResult,
    InstanceSceneResult,
    RenameNodeResult,
    SaveSceneResult,
    SetPropertyResult,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_confirmation,
    require_node_exists,
)
from mcp_server.tools._route import route

SCENE_EDIT = {SCENE_EDIT_TAG}


def register_mutation(mcp: FastMCP, bridge: Bridge) -> None:
    """Register all eight mutation tools on the server."""

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def create_node(
        parent_path: str, node_type: str, node_name: str, dry_run: bool = False
    ) -> CreateNodeResult:
        """Create a node of ``node_type`` named ``node_name`` under ``parent_path``
        (scene-relative; "." is the root). Reversible via the editor's undo.
        """
        await require_active_scene(bridge)
        await require_node_exists(bridge, parent_path)
        if dry_run:
            # Mirror the addon's scene-relative path (root children have no "./").
            preview = node_name if parent_path in (".", "") else f"{parent_path}/{node_name}"
            return CreateNodeResult(node_path=preview, created=False, dry_run=True)
        params = {"parent_path": parent_path, "node_type": node_type, "name": node_name}
        return CreateNodeResult(**await route(bridge, "cmd_create_node", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def rename_node(node_path: str, new_name: str, dry_run: bool = False) -> RenameNodeResult:
        """Rename the node at ``node_path`` to ``new_name``."""
        await require_node_exists(bridge, node_path)
        if dry_run:
            return RenameNodeResult(
                node_path=node_path, new_name=new_name, renamed=False, dry_run=True
            )
        params = {"node_path": node_path, "new_name": new_name}
        return RenameNodeResult(**await route(bridge, "cmd_rename_node", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def set_node_property(
        node_path: str, property: str, value: Any, dry_run: bool = False
    ) -> SetPropertyResult:
        """Set ``property`` on the node at ``node_path`` to ``value``. Godot types
        (Vector2/3, Color, Rect2 as objects; NodePath as string) are coerced by the
        addon to match the property's declared type.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return SetPropertyResult(
                node_path=node_path, property=property, value=value, set=False, dry_run=True
            )
        params = {"node_path": node_path, "property": property, "value": value}
        return SetPropertyResult(**await route(bridge, "cmd_set_node_property", params))

    @mcp.tool(meta=DESTRUCTIVE, tags=SCENE_EDIT)
    @enforce_preconditions
    async def delete_node(
        node_path: str, confirm: bool = False, dry_run: bool = False
    ) -> DeleteNodeResult:
        """Delete the node at ``node_path``. Destructive: requires ``confirm=True``
        to actually delete (``dry_run=True`` previews without confirming).
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return DeleteNodeResult(node_path=node_path, deleted=False, dry_run=True)
        require_confirmation(confirm, "delete_node")
        params = {"node_path": node_path, "confirm": True}
        return DeleteNodeResult(**await route(bridge, "cmd_delete_node", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def attach_script(
        node_path: str, script_path: str, dry_run: bool = False
    ) -> AttachScriptResult:
        """Attach the existing script at ``script_path`` (a ``res://`` path) to the
        node at ``node_path``.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return AttachScriptResult(
                node_path=node_path, script_path=script_path, attached=False, dry_run=True
            )
        params = {"node_path": node_path, "script_path": script_path}
        return AttachScriptResult(**await route(bridge, "cmd_attach_script", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def connect_signal(
        source_path: str,
        signal_name: str,
        target_path: str,
        method_name: str,
        dry_run: bool = False,
    ) -> ConnectSignalResult:
        """Connect ``signal_name`` on the source node to ``method_name`` on the
        target node (persisted into the scene).
        """
        await require_node_exists(bridge, source_path)
        await require_node_exists(bridge, target_path)
        if dry_run:
            return ConnectSignalResult(
                source_path=source_path,
                signal_name=signal_name,
                target_path=target_path,
                method_name=method_name,
                connected=False,
                dry_run=True,
            )
        params = {
            "source_path": source_path,
            "signal_name": signal_name,
            "target_path": target_path,
            "method_name": method_name,
        }
        return ConnectSignalResult(**await route(bridge, "cmd_connect_signal", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def save_scene(dry_run: bool = False) -> SaveSceneResult:
        """Save the currently open scene to disk, reporting the file path."""
        await require_active_scene(bridge)
        if dry_run:
            return SaveSceneResult(saved=False, dry_run=True)
        return SaveSceneResult(**await route(bridge, "cmd_save_scene"))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def create_scene(
        root_type: str, scene_path: str, dry_run: bool = False
    ) -> CreateSceneResult:
        """Create a new scene file at ``scene_path`` (``res://…​.tscn``) with a root
        node of ``root_type``, and open it for editing.
        """
        require_bridge_connected(bridge)
        if dry_run:
            return CreateSceneResult(
                scene_path=scene_path, root_type=root_type, created=False, dry_run=True
            )
        params = {"root_type": root_type, "scene_path": scene_path}
        return CreateSceneResult(**await route(bridge, "cmd_create_scene", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def instance_scene(
        parent_path: str, scene_path: str, name: str = "", dry_run: bool = False
    ) -> InstanceSceneResult:
        """Instance a saved scene (``scene_path``, a ``res://…​.tscn``) as a child of
        ``parent_path``. This is the core Godot authoring move for composing scenes
        from reusable parts. Returns the new instance's scene-relative path.
        """
        await require_active_scene(bridge)
        await require_node_exists(bridge, parent_path)
        if dry_run:
            preview = name if parent_path in (".", "") else f"{parent_path}/{name}"
            return InstanceSceneResult(
                node_path=preview, scene_path=scene_path, instanced=False, dry_run=True
            )
        params = {"parent_path": parent_path, "scene_path": scene_path, "name": name}
        return InstanceSceneResult(**await route(bridge, "cmd_instance_scene", params))
