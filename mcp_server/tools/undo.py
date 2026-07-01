"""Core `godot_undo` tool: pop the editor undo history N steps (S4)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.safety import MUTATING
from mcp_server.tools._route import route


def register_undo(mcp: FastMCP, bridge: Bridge) -> None:
    @mcp.tool(meta=MUTATING, tags={CORE_TAG})
    async def undo(count: int = 1, dry_run: bool = False) -> dict[str, Any]:
        """Undo the last ``count`` editor actions on the current scene's history.

        With ``dry_run=True``, previews (``has_undo`` + ``would_undo_next``) without
        undoing. Otherwise returns ``{undone, requested, last_action,
        nothing_to_undo}``. Undoing an empty history is a no-op (``undone == 0``,
        ``nothing_to_undo == True``), not an error — the reversibility ledger decides
        what that means.
        """
        if count < 1:
            raise ToolError("count must be >= 1")  # structured, pre-bridge
        result = await route(bridge, "cmd_undo", {"count": count, "dry_run": dry_run})
        if not dry_run:
            result["nothing_to_undo"] = result.get("undone", 0) == 0
        return result
