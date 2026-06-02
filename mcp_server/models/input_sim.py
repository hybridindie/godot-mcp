"""Typed results for input simulation tools (issue #36)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SimInputResult(BaseModel):
    sent: bool
    kind: str = ""
    count: int = 1  # events sent (1 for a single event; N for a sequence)


class InputStatsResult(BaseModel):
    playing: bool
    connected: bool = False
    injected: int = 0  # synthesized input events the running game has acknowledged


class RecordResult(BaseModel):
    recording: bool


class RecordingResult(BaseModel):
    ready: bool = False
    connected: bool = False
    # Captured events in the play_input_sequence format — pass straight to that tool.
    events: list[dict[str, Any]] = Field(default_factory=list)
