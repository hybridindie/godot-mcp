"""Core history tools: `godot_undo` (S4), `godot_redo` + `godot_list_history` (#529).

All three drive the current scene's EditorUndoRedoManager history over the
bridge (``cmd_undo`` / ``cmd_redo`` / ``cmd_list_history``); the server owns
the safety classes and the ``count >= 1`` validation.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.models.undo import HistoryResult, RedoResult, UndoResult
from mcp_server.safety import MUTATING, READ_ONLY
from mcp_server.tools._route import route


def register_undo(mcp: FastMCP, bridge: Bridge) -> None:
    # UndoResult/RedoResult drop mode-irrelevant None fields via a
    # @model_serializer, which hides their fields from pydantic's
    # serialization-mode schema generation (issue #385) — FastMCP's auto-derived
    # outputSchema degenerates to {additionalProperties: true}. Declare the
    # validation-mode (field-derived) schema explicitly: both emission shapes
    # (real op, dry-run preview) are subsets of it, so clients can type-check
    # either.
    @mcp.tool(
        meta=MUTATING,
        tags={CORE_TAG},
        output_schema=UndoResult.model_json_schema(),
    )
    async def undo(count: int = 1, dry_run: bool = False) -> UndoResult:
        """Undo the last ``count`` editor actions on the current scene's history.

        With ``dry_run=True``, previews (``has_undo`` + ``would_undo_next``) without
        undoing. Otherwise returns ``{undone, requested, last_action,
        nothing_to_undo}``. Undoing an empty history is a no-op (``undone == 0``,
        ``nothing_to_undo == True``), not an error — the reversibility ledger decides
        what that means.

        No node/scene target to precondition — ``route()`` already surfaces a
        disconnected bridge as a structured ``BRIDGE_DISCONNECTED`` error.
        """
        if count < 1:
            raise ToolError("count must be >= 1")  # structured, pre-bridge
        result = await route(bridge, "cmd_undo", {"count": count, "dry_run": dry_run})
        # dry_run is authoritative from our own arg, not the addon echo; requested
        # likewise falls back to count if the addon omitted it.
        result["dry_run"] = dry_run
        result.setdefault("requested", count)
        if not dry_run:
            result["nothing_to_undo"] = result.get("undone", 0) == 0
        # UndoResult(**result) validates the addon payload and drops mode-irrelevant
        # (None) keys on serialization (see UndoResult's @model_serializer).
        return UndoResult(**result)

    # --- #529: redo parity + history introspection -------------------------
    @mcp.tool(
        meta=MUTATING,
        tags={CORE_TAG},
        output_schema=RedoResult.model_json_schema(),
    )
    async def redo(count: int = 1, dry_run: bool = False) -> RedoResult:
        """Redo the last ``count`` undone editor actions on the current scene's history.

        The mirror of ``godot_undo``: with ``dry_run=True``, previews (``has_redo`` +
        ``would_redo_next``) without redoing; otherwise returns ``{redone, requested,
        last_action, nothing_to_redo}``. Redoing with nothing to redo is a no-op
        (``redone == 0``, ``nothing_to_redo == True``), not an error. Use
        ``godot_list_history`` first when unsure which direction is available.
        """
        if count < 1:
            raise ToolError("count must be >= 1")  # structured, pre-bridge
        result = await route(bridge, "cmd_redo", {"count": count, "dry_run": dry_run})
        result["dry_run"] = dry_run
        result.setdefault("requested", count)
        if not dry_run:
            result["nothing_to_redo"] = result.get("redone", 0) == 0
        return RedoResult(**result)

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def list_history() -> HistoryResult:
        """Inspect the current scene's editor undo history before mutating.

        Returns the version counter (increments on every committed action — a
        cheap change-detector), ``has_undo`` / ``has_redo`` availability, the
        current action name, the history depth, and the most recent action
        names (capped, most recent last). Empty history returns zero-values,
        not an error. Use it to orient before ``godot_undo`` / ``godot_redo``.
        """
        result = await route(bridge, "cmd_list_history", {})
        # Coerce the addon's recent-names array into typed entries; a missing
        # key degrades honestly to an empty list rather than failing the call.
        recent = result.get("recent", [])
        result["recent"] = [{"name": str(n)} for n in recent]
        return HistoryResult(**result)