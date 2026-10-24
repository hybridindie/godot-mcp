"""Undo checkpoint models (#760)."""

from __future__ import annotations

from pydantic import BaseModel


class CheckpointInfo(BaseModel):
    """A named marker on the current scene's undo history."""

    checkpoint_id: str
    label: str | None = None
    scene_path: str | None = None
    current_action: int
    history_count: int
    created_at: float | None = None


class CheckpointRestoreResult(BaseModel):
    checkpoint_id: str
    label: str | None = None
    scene_path: str | None = None
    requested: int = 0
    undone: int = 0
    complete: bool = False
    dry_run: bool = False
    hint: str | None = None
