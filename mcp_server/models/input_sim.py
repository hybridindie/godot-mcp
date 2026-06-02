"""Typed results for input simulation tools (issue #36)."""

from __future__ import annotations

from pydantic import BaseModel


class SimInputResult(BaseModel):
    sent: bool
    kind: str = ""
    count: int = 1  # events sent (1 for a single event; N for a sequence)


class InputStatsResult(BaseModel):
    playing: bool
    connected: bool = False
    injected: int = 0  # synthesized input events the running game has acknowledged
