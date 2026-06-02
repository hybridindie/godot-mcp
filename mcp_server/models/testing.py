"""Typed results for testing / QA tools (issue #37)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssertionResult(BaseModel):
    node_path: str
    property: str
    op: str
    expected: Any = None
    actual: Any = None
    passed: bool = False
    error: str = ""


class ScenarioResult(BaseModel):
    passed: bool = False
    played: bool = False
    connected: bool = False
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: str = ""


class ScreenshotDiffResult(BaseModel):
    same_size: bool
    width: int = 0
    height: int = 0
    diff_pixels: int = 0
    total_pixels: int = 0
    diff_ratio: float = 0.0
    mean_abs_diff: float = 0.0
    match: bool = False


class StressTestResult(BaseModel):
    survived: bool
    iterations: int
    playing_after: bool
    seed: int
    error: str = ""
