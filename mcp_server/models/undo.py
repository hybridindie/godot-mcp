"""Typed results for the core history tools: ``godot_undo`` (S4), ``godot_redo``
and ``godot_list_history`` (#529).

A single model covers each tool's response shapes; the mode-specific fields
default to ``None`` and are dropped on serialization (a ``model_serializer``
skips the ``None`` fields) so a dry-run preview never carries a
``nothing_to_undo`` key and a real undo never carries the preview-only
``has_undo``/``would_undo_next`` keys.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_serializer


class _UndoRedoResult(BaseModel):
    """Shared shape for the undo/redo results (#799).

    Both models emit ``dry_run``/``requested``/``reversible_by`` plus only the
    mode-relevant fields. ``_MODE_FIELDS`` names those per subclass; a ``None``
    value means "not this mode" and is dropped on serialization, so a dry-run
    preview never carries ``nothing_to_undo`` and a real undo never carries
    ``has_undo``/``would_undo_next``.

    A ``model_serializer`` (not a ``model_dump`` override) is used because
    FastMCP builds ``structured_content`` via pydantic-core serialization, which
    only honors this hook.
    """

    model_config = ConfigDict(extra="ignore")

    dry_run: bool
    requested: int
    reversible_by: Literal["undo", "vcs", "none"] = "undo"

    _MODE_FIELDS: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        data = {
            "dry_run": self.dry_run,
            "requested": self.requested,
            "reversible_by": self.reversible_by,
        }
        for field in self._MODE_FIELDS:
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        return data


class UndoResult(_UndoRedoResult):
    # Real-undo fields (absent on a dry-run preview).
    undone: int | None = None
    last_action: str | None = None
    nothing_to_undo: bool | None = None

    # Dry-run preview fields (absent on a real undo).
    has_undo: bool | None = None
    would_undo_next: str | None = None

    _MODE_FIELDS: ClassVar[tuple[str, ...]] = (
        "undone",
        "last_action",
        "nothing_to_undo",
        "has_undo",
        "would_undo_next",
    )


class RedoResult(_UndoRedoResult):
    # Real-redo fields (absent on a dry-run preview).
    redone: int | None = None
    last_action: str | None = None
    nothing_to_redo: bool | None = None

    # Dry-run preview fields (absent on a real redo).
    has_redo: bool | None = None
    would_redo_next: str | None = None

    _MODE_FIELDS: ClassVar[tuple[str, ...]] = (
        "redone",
        "last_action",
        "nothing_to_redo",
        "has_redo",
        "would_redo_next",
    )


class HistoryEntry(BaseModel):
    """One editor undo-history action, named for agent orientation."""

    name: str


class HistoryResult(BaseModel):
    """``godot_list_history`` response: the editor history's orientation data.

    ``version`` increments on every committed action — a cheap change-detector
    the agent can compare across calls. ``depth`` counts the history entries
    (``get_history_count``, 4.4+); ``recent`` names up to 20 entries, most
    recent last (``get_action_name`` indices are 0-based over the history).
    ``can_redo`` is the #529 ticket's field name — a documented alias of
    ``has_redo``, emitted so the envelope matches the issue's field list.
    """

    model_config = ConfigDict(extra="ignore")

    version: int
    has_undo: bool
    has_redo: bool
    can_redo: bool
    current_action: str
    depth: int
    recent: list[HistoryEntry]