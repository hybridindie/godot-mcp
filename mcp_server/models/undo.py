"""Typed results for the core history tools: ``godot_undo`` (S4), ``godot_redo``
and ``godot_list_history`` (#529).

A single model covers each tool's response shapes; the mode-specific fields
default to ``None`` and are dropped on serialization (a ``model_serializer``
skips the ``None`` fields) so a dry-run preview never carries a
``nothing_to_undo`` key and a real undo never carries the preview-only
``has_undo``/``would_undo_next`` keys.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer

_UNDO_REDO_FIELDS = (
    "undone",
    "last_action",
    "nothing_to_undo",
    "has_undo",
    "would_undo_next",
)


class UndoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dry_run: bool
    requested: int

    # Real-undo fields (absent on a dry-run preview).
    undone: int | None = None
    last_action: str | None = None
    nothing_to_undo: bool | None = None

    # Dry-run preview fields (absent on a real undo).
    has_undo: bool | None = None
    would_undo_next: str | None = None

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        # Drop null fields so each mode serializes only its own keys: a dry-run
        # preview never emits ``nothing_to_undo``; a real undo never emits the
        # preview-only ``has_undo``/``would_undo_next``. A model_serializer (not a
        # model_dump override) is used because FastMCP builds structured_content via
        # pydantic-core serialization, which only honors this hook.
        data = {"dry_run": self.dry_run, "requested": self.requested}
        for field in _UNDO_REDO_FIELDS:
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        return data


_REDO_REDO_FIELDS = (
    "redone",
    "last_action",
    "nothing_to_redo",
    "has_redo",
    "would_redo_next",
)


class RedoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dry_run: bool
    requested: int

    # Real-redo fields (absent on a dry-run preview).
    redone: int | None = None
    last_action: str | None = None
    nothing_to_redo: bool | None = None

    # Dry-run preview fields (absent on a real redo).
    has_redo: bool | None = None
    would_redo_next: str | None = None

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        # Mirrors UndoResult: drop mode-irrelevant None fields so both emission
        # shapes validate against the one declared schema (#385 family).
        data = {"dry_run": self.dry_run, "requested": self.requested}
        for field in _REDO_REDO_FIELDS:
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        return data


class HistoryEntry(BaseModel):
    """One editor undo-history action, named for agent orientation."""

    name: str


class HistoryResult(BaseModel):
    """``godot_list_history`` response: the editor history's orientation data.

    ``version`` increments on every committed action — a cheap change-detector
    the agent can compare across calls. ``depth`` counts the history entries
    (``get_history_count``, 4.4+); ``recent`` names up to 20 entries, most
    recent last (``get_action_name`` indices are 0-based over the history).
    """

    model_config = ConfigDict(extra="ignore")

    version: int
    has_undo: bool
    has_redo: bool
    current_action: str
    depth: int
    recent: list[HistoryEntry]