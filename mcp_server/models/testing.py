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


class TestFailure(BaseModel):
    """One failing test, as scraped from the runner's output (best-effort detail)."""

    test: str = ""
    file: str | None = None
    line: int | None = None
    message: str = ""


class RunTestsResult(BaseModel):
    """Structured result of a headless test-suite run (issue #206).

    A neutral capability — execute the project's test suite and report results.
    It encodes no TDD workflow; the agent composes it. ``framework_absent`` is a
    normal (non-error) outcome so the caller can fall back gracefully.
    """

    ran: bool
    framework: str | None = None
    framework_absent: bool = False
    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[TestFailure] = Field(default_factory=list)
    timed_out: bool = False
    exit_code: int | None = None
    raw_summary: str = ""
