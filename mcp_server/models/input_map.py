"""Typed results for input map editing tools (issue #81).

Editing the project's Input Map actions and events (project.godot).
"""

from __future__ import annotations

from pydantic import BaseModel


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
