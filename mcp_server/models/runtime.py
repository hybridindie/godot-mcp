"""Typed results for the runtime loop (issue #13)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """A parsed error or warning from a run's output."""

    type: str  # "error" | "warning"
    message: str
    source: str | None = None  # e.g. "res://script.gd:42" or "at: …" when present
    line: int | None = None


class RunCaptureResult(BaseModel):
    """Outcome of running the project headless and capturing its output."""

    ran: bool  # the process launched and produced output
    exit_code: int | None = None  # None when killed by timeout
    timed_out: bool = False
    duration_seconds: float = 0.0
    errors: list[LogEntry] = Field(default_factory=list)
    warnings: list[LogEntry] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)  # non-error print lines
    command: list[str] = Field(default_factory=list)
