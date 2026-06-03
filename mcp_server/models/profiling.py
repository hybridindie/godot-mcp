"""Typed results for profiling tools (issue #38)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EditorPerformanceResult(BaseModel):
    monitors: dict[str, float] = Field(default_factory=dict)


class GamePerformanceResult(BaseModel):
    playing: bool = False
    connected: bool = False
    # False when the probe snapshot hasn't arrived within timeout_ms (monitors may be empty).
    ready: bool = False
    monitors: dict[str, float] = Field(default_factory=dict)
    hint: str = ""
