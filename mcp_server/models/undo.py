"""Typed result for the core ``godot_undo`` tool (S4).

A single model covers both response shapes; the mode-specific fields default to
``None`` and are dropped on serialization (a ``model_serializer`` skips the ``None``
fields) so a dry-run preview never carries a ``nothing_to_undo`` key and a real undo
never carries the preview-only ``has_undo``/``would_undo_next`` keys.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer


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
        for field in ("undone", "last_action", "nothing_to_undo", "has_undo", "would_undo_next"):
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        return data
