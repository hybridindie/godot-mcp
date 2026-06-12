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

import asyncio
import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

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
    ApprovalGate,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_confirmation,
    require_node_exists,
)
from mcp_server.suggestions import suggest
from mcp_server.tools._route import route, run_or_preview

SCENE_EDIT = {SCENE_EDIT_TAG}


async def _node_property_names(bridge: Bridge, node_path: str) -> list[str]:
    """Fetch the full property list for a node from the addon.
    Returns ``[]`` on any non-cancellation failure (best-effort).
    """
    try:
        resp = await bridge.send(
            "cmd_get_node_property_list", {"node_path": node_path}
        )
        if resp.ok and resp.result:
            return [str(p) for p in resp.result.get("properties", [])]
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    return []


async def _try_set_with_suggestions(
    bridge: Bridge,
    params: dict[str, Any],
    node_path: str,
    property: str,
) -> SetPropertyResult:
    """Route to the addon; on property-not-found enrich the error with suggestions."""
    try:
        result = await route(bridge, "cmd_set_node_property", params)
        return SetPropertyResult(**result)
    except ToolError as exc:
        text = str(exc)
        if "has no property" in text:
            props = await _node_property_names(bridge, node_path)
            sug = suggest(property, props)
            if sug:
                hint = (
                    f"Node has no property '{property}'."
                    f" Did you mean: {', '.join(sug)}?"
                    f" [suggestions={json.dumps(sug)}]"
                )
            else:
                hint = f"Node has no property '{property}'."
            raise ToolError(f"VALIDATION_ERROR: {hint}") from None
        raise


def register_mutation(
    mcp: FastMCP, bridge: Bridge, approval: ApprovalGate | None = None
) -> None:
    """Register all eight mutation tools on the server."""
    approval = approval or ApprovalGate()

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def create_node(
        parent_path: str, node_type: str, node_name: str, dry_run: bool = False
    ) -> CreateNodeResult:
        """Create a node of ``node_type`` named ``node_name`` under ``parent_path``
        (scene-relative; "." is the root). Reversible via the editor's undo.

        IF THIS FAILS with "active_scene":
          -> No scene is open. Call open_scene(path) or create_scene(path) first.
        IF THIS FAILS with "parent not found":
          -> parent_path is wrong. Use get_scene_tree() to see actual node paths.
        """
        await require_active_scene(bridge)
        await require_node_exists(bridge, parent_path)
        preview = node_name if parent_path in (".", "") else f"{parent_path}/{node_name}"
        params = {"parent_path": parent_path, "node_type": node_type, "name": node_name}
        return await run_or_preview(
            dry_run,
            CreateNodeResult,
            {"node_path": preview, "created": False},
            bridge,
            "cmd_create_node",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def rename_node(node_path: str, new_name: str, dry_run: bool = False) -> RenameNodeResult:
        """Rename the node at ``node_path`` to ``new_name``."""
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "new_name": new_name}
        preview = {"node_path": node_path, "new_name": new_name, "renamed": False}
        return await run_or_preview(
            dry_run, RenameNodeResult, preview, bridge, "cmd_rename_node", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def set_node_property(
        node_path: str, property: str, value: Any, dry_run: bool = False
    ) -> SetPropertyResult:
        """Set ``property`` on the node at ``node_path`` to ``value``. Godot types
        (Vector2/3, Color, Rect2 as objects; NodePath as string) are coerced by the
        addon to match the property's declared type.

        IF THIS FAILS with "Node not found":
          -> node_path is wrong. Use get_scene_tree() to see actual paths.
        IF THIS FAILS with "has no property":
          -> The property name is wrong. Use get_node_property_list(node_path) to
             see valid property names for that node type.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "property": property, "value": value}
        preview = {"node_path": node_path, "property": property, "value": value, "set": False}
        if dry_run:
            return SetPropertyResult(**preview, dry_run=True)
        return await _try_set_with_suggestions(bridge, params, node_path, property)

    @mcp.tool(meta=DESTRUCTIVE, tags=SCENE_EDIT)
    @enforce_preconditions
    async def delete_node(
        node_path: str, confirm: bool = False, dry_run: bool = False
    ) -> DeleteNodeResult:
        """Delete the node at ``node_path``. Destructive: requires ``confirm=True``
        to actually delete (``dry_run=True`` previews without confirming).
        """
        await require_node_exists(bridge, node_path)
        if not dry_run:
            require_confirmation(confirm, "delete_node")
            await approval.require("delete_node", "destructive", {"node_path": node_path})
        params = {"node_path": node_path, "confirm": True}
        preview = {"node_path": node_path, "deleted": False}
        return await run_or_preview(
            dry_run, DeleteNodeResult, preview, bridge, "cmd_delete_node", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def attach_script(
        node_path: str, script_path: str, dry_run: bool = False
    ) -> AttachScriptResult:
        """Attach the existing script at ``script_path`` (a ``res://`` path) to the
        node at ``node_path``.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "script_path": script_path}
        preview = {"node_path": node_path, "script_path": script_path, "attached": False}
        return await run_or_preview(
            dry_run, AttachScriptResult, preview, bridge, "cmd_attach_script", params
        )

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
        params = {
            "source_path": source_path,
            "signal_name": signal_name,
            "target_path": target_path,
            "method_name": method_name,
        }
        preview = {
            "source_path": source_path,
            "signal_name": signal_name,
            "target_path": target_path,
            "method_name": method_name,
            "connected": False,
        }
        return await run_or_preview(
            dry_run, ConnectSignalResult, preview, bridge, "cmd_connect_signal", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def save_scene(dry_run: bool = False) -> SaveSceneResult:
        """Save the currently open scene to disk, reporting the file path."""
        await require_active_scene(bridge)
        preview = {"saved": False}
        return await run_or_preview(
            dry_run, SaveSceneResult, preview, bridge, "cmd_save_scene"
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def create_scene(
        root_type: str, scene_path: str, dry_run: bool = False
    ) -> CreateSceneResult:
        """Create a new scene file at ``scene_path`` (``res://…​.tscn``) with a root
        node of ``root_type``, and open it for editing.
        """
        require_bridge_connected(bridge)
        params = {"root_type": root_type, "scene_path": scene_path}
        preview = {"scene_path": scene_path, "root_type": root_type, "created": False}
        return await run_or_preview(
            dry_run, CreateSceneResult, preview, bridge, "cmd_create_scene", params
        )

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
        # Deterministic fallback: use scene file name (without extension) when name is empty,
        # matching what the addon creates by default.
        _name = name or Path(scene_path).stem
        preview = _name if parent_path in (".", "") else f"{parent_path}/{_name}"
        params = {"parent_path": parent_path, "scene_path": scene_path, "name": name}
        return await run_or_preview(
            dry_run,
            InstanceSceneResult,
            {"node_path": preview, "scene_path": scene_path, "instanced": False},
            bridge,
            "cmd_instance_scene",
            params,
        )
