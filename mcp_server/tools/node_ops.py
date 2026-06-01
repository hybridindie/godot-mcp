"""Node-parity tools (issue #31).

Rounds out node editing beyond create/rename/set/delete: duplicate, move/reparent,
group membership, and signal-connection listing/disconnect. Extends the gated
`scene_edit` toolset. Mutating ops are UndoRedo-wrapped addon-side and support
``dry_run``; signal listing is ``read_only``.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SCENE_EDIT_TAG
from mcp_server.models.node_ops import (
    DisconnectSignalResult,
    DuplicateNodeResult,
    GroupResult,
    MoveNodeResult,
    SignalConnectionList,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

SCENE_EDIT = {SCENE_EDIT_TAG}


def register_node_ops(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the node-parity tools (in the scene_edit toolset)."""

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def duplicate_node(node_path: str, dry_run: bool = False) -> DuplicateNodeResult:
        """Duplicate the node at ``node_path`` (with its subtree) under the same parent.
        Returns the new node's path. Reversible via undo.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return DuplicateNodeResult(node_path="", source_path=node_path, dry_run=True)
        result = await route(bridge, "cmd_duplicate_node", {"node_path": node_path})
        return DuplicateNodeResult(**result)

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def move_node(
        node_path: str, new_parent_path: str, index: int = -1, dry_run: bool = False
    ) -> MoveNodeResult:
        """Reparent the node at ``node_path`` under ``new_parent_path`` (optionally at
        ``index``; -1 appends). Cannot move the root or into a descendant. Reversible.
        """
        await require_node_exists(bridge, node_path)
        await require_node_exists(bridge, new_parent_path)
        if dry_run:
            return MoveNodeResult(node_path=node_path, moved=False, dry_run=True)
        params = {"node_path": node_path, "new_parent_path": new_parent_path, "index": index}
        return MoveNodeResult(**await route(bridge, "cmd_move_node", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def add_to_group(node_path: str, group: str, dry_run: bool = False) -> GroupResult:
        """Add the node to ``group`` (persistent — saved into the scene). Reversible."""
        await require_node_exists(bridge, node_path)
        if dry_run:
            return GroupResult(
                node_path=node_path, group=group, in_group=True, changed=False, dry_run=True
            )
        result = await route(bridge, "cmd_add_to_group", {"node_path": node_path, "group": group})
        return GroupResult(node_path=node_path, group=group, in_group=True, changed=result["added"])

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def remove_from_group(node_path: str, group: str, dry_run: bool = False) -> GroupResult:
        """Remove the node from ``group``. Reversible via undo."""
        await require_node_exists(bridge, node_path)
        if dry_run:
            return GroupResult(
                node_path=node_path, group=group, in_group=False, changed=False, dry_run=True
            )
        result = await route(
            bridge, "cmd_remove_from_group", {"node_path": node_path, "group": group}
        )
        return GroupResult(
            node_path=node_path, group=group, in_group=False, changed=result["removed"]
        )

    @mcp.tool(meta=READ_ONLY, tags=SCENE_EDIT)
    @enforce_preconditions
    async def list_signal_connections(node_path: str) -> SignalConnectionList:
        """List the outgoing signal connections from the node at ``node_path``
        ({ signal, target_path, method, persistent }).
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path}
        return SignalConnectionList(**await route(bridge, "cmd_list_signal_connections", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_EDIT)
    @enforce_preconditions
    async def disconnect_signal(
        source_path: str,
        signal_name: str,
        target_path: str,
        method_name: str,
        dry_run: bool = False,
    ) -> DisconnectSignalResult:
        """Disconnect ``signal_name`` on the source node from ``method_name`` on the
        target node. Reversible via undo.
        """
        await require_node_exists(bridge, source_path)
        await require_node_exists(bridge, target_path)
        if dry_run:
            return DisconnectSignalResult(
                source_path=source_path,
                signal_name=signal_name,
                target_path=target_path,
                method_name=method_name,
                disconnected=False,
                dry_run=True,
            )
        params = {
            "source_path": source_path,
            "signal_name": signal_name,
            "target_path": target_path,
            "method_name": method_name,
        }
        return DisconnectSignalResult(**await route(bridge, "cmd_disconnect_signal", params))
