"""Undo checkpoints (#760): mark a point and undo back to it.

Checkpoints live in the server process and reference the current scene's undo
history. They cover **UndoRedo-tracked** actions only — file writes, project
settings and over-threshold batches are outside the undo stack (the VCS snapshot
backstop is the follow-up for those). A checkpoint is intentionally not durable
across a server restart.
"""

from __future__ import annotations

import time
from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.models.checkpoints import CheckpointInfo, CheckpointRestoreResult
from mcp_server.models.envelope import ErrorCode
from mcp_server.safety import (
    MUTATING,
    READ_ONLY,
    PreconditionError,
    enforce_preconditions,
)
from mcp_server.tools._route import route

_MAX_CHECKPOINTS = 50


def _state(result: dict[str, Any]) -> dict[str, Any]:
    if not bool(result.get("available", False)):
        raise PreconditionError(
            "No undo history is available for the current scene.",
            required="undo_history",
        )
    return result


def _checkpoint_error(hint: str, required: str) -> PreconditionError:
    return PreconditionError(
        hint, required=required, error=ErrorCode.RESOURCE_NOT_FOUND
    )


def register_checkpoints(mcp: FastMCP, bridge: Bridge) -> None:
    """Register checkpoint_create / checkpoint_restore (core)."""
    store: dict[str, dict[str, Any]] = {}
    counter = 0

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    @enforce_preconditions
    async def checkpoint_create(label: str = "") -> CheckpointInfo:
        """Mark the current scene's undo history; returns an id for checkpoint_restore.
        UndoRedo-tracked actions only (file writes/settings/over-threshold batches
        are outside the undo stack)."""
        nonlocal counter
        state = _state(await route(bridge, "cmd_undo_state"))
        counter += 1
        checkpoint_id = f"cp{counter}"
        entry: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "label": label or None,
            "scene_path": state.get("scene_path"),
            "current_action": int(state.get("current", 0)),
            "history_count": int(state.get("count", 0)),
            "created_at": time.time(),
        }
        store[checkpoint_id] = entry
        while len(store) > _MAX_CHECKPOINTS:
            store.pop(next(iter(store)))
        return CheckpointInfo(**entry)

    @mcp.tool(meta=MUTATING, tags={CORE_TAG})
    @enforce_preconditions
    async def checkpoint_restore(
        checkpoint_id: str, dry_run: bool = False
    ) -> CheckpointRestoreResult:
        """Undo back to a checkpoint; dry_run reports the delta without changing
        the editor. UndoRedo-tracked actions only."""
        checkpoint = store.get(checkpoint_id)
        if checkpoint is None:
            raise _checkpoint_error(
                f"No checkpoint '{checkpoint_id}'. Create one with checkpoint_create.",
                "checkpoint_id",
            )
        state = _state(await route(bridge, "cmd_undo_state"))
        if state.get("scene_path") != checkpoint["scene_path"]:
            raise PreconditionError(
                f"Checkpoint '{checkpoint_id}' belongs to "
                f"'{checkpoint['scene_path'] or '(no scene)'}', but the active scene is "
                f"'{state.get('scene_path') or '(none)'}'.",
                required="checkpoint_scene",
            )
        if int(state.get("count", 0)) < int(checkpoint["history_count"]):
            raise PreconditionError(
                f"Checkpoint '{checkpoint_id}' is stale: the undo history was cleared "
                "or replaced after it was created. Create a new checkpoint.",
                required="checkpoint_history",
            )
        steps = int(state.get("current", 0)) - int(checkpoint["current_action"])
        if steps < 0:
            raise PreconditionError(
                f"Checkpoint '{checkpoint_id}' is ahead of the current undo position; "
                "restore only moves backward (redo manually first).",
                required="checkpoint_behind",
            )
        if steps == 0:
            return CheckpointRestoreResult(
                checkpoint_id=checkpoint_id,
                label=checkpoint["label"],
                scene_path=checkpoint["scene_path"],
                requested=0,
                undone=0,
                complete=True,
                dry_run=dry_run,
            )
        if dry_run:
            return CheckpointRestoreResult(
                checkpoint_id=checkpoint_id,
                label=checkpoint["label"],
                scene_path=checkpoint["scene_path"],
                requested=steps,
                undone=0,
                complete=False,
                dry_run=True,
                hint="Preview only; the editor history was not changed.",
            )
        undone = int((await route(bridge, "cmd_undo", {"count": steps})).get("undone", 0))
        complete = undone == steps
        hint = None
        if not complete:
            hint = (
                f"Only {undone} of {steps} actions were undone; the undo stack ended "
                "earlier than the checkpoint expected."
            )
        elif steps:
            hint = (
                "UndoRedo-tracked actions restored; file writes, project settings and "
                "over-threshold batches are outside the undo stack."
            )
        return CheckpointRestoreResult(
            checkpoint_id=checkpoint_id,
            label=checkpoint["label"],
            scene_path=checkpoint["scene_path"],
            requested=steps,
            undone=undone,
            complete=complete,
            dry_run=False,
            hint=hint,
        )
