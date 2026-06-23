"""Typed results for input map editing tools (issue #81).

Editing the project's Input Map actions and events (project.godot).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AddInputActionResult(BaseModel):
    name: str
    added: bool
    deadzone: float = 0.5
    dry_run: bool = False


class RemoveInputActionResult(BaseModel):
    name: str
    removed: bool
    dry_run: bool = False


class AddInputEventResult(BaseModel):
    action: str
    event_index: int = 0
    added: bool
    dry_run: bool = False


class ClearInputActionEventsResult(BaseModel):
    action: str
    cleared: bool
    dry_run: bool = False


class InputActionEvents(BaseModel):
    """An input action's deadzone + its events (issue #219 P2) — the inverse of
    ``add_input_event`` / ``clear_input_action_events`` / ``remove_input_action``. Each
    event is a dict in the same shape ``add_input_event`` accepts (``event_type`` plus
    its kind-specific keys: ``keycode``/modifiers for key, ``button`` for mouse,
    ``device``/``joy_button_index`` or ``axis``/``axis_value`` for joypad), so the action
    can be rebuilt for rollback."""

    action: str
    deadzone: float = 0.5
    events: list[dict[str, Any]] = Field(default_factory=list)
