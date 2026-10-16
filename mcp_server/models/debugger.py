"""Typed results for debugger breakpoint control tools (issue #110, Tier 1 + Tier 2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BreakpointResult(BaseModel):
    """Outcome of setting or removing a single breakpoint."""

    breakpoint_set: bool = False
    breakpoint_removed: bool = False
    path: str = ""
    line: int = 0


class ClearBreakpointsResult(BaseModel):
    """Outcome of clearing all breakpoints."""

    breakpoints_cleared: bool = False


class ForceBreakResult(BaseModel):
    """Outcome of requesting a forced break in the running game."""

    force_break_sent: bool = False
    # Whether the debugger session is (now) in a break state. False means the
    # break was requested but the game has not entered the debug loop (issue
    # #411) — e.g. no probe cooperation; treat stack tools as unreliable.
    breaked: bool = False


class StepResult(BaseModel):
    """Outcome of a debugger step command."""

    stepped: bool = False


class ContinueResult(BaseModel):
    """Outcome of resuming execution after a breakpoint."""

    running: bool = False


class StackFramesResult(BaseModel):
    """Outcome of requesting the current call stack."""

    frames: list[dict[str, Any]] = Field(default_factory=list)
    # Present when frames:[] means "no reply cached yet" rather than "empty
    # stack" — the poll-and-cache reply is async (issue #411).
    hint: str = ""


class EvaluationResult(BaseModel):
    """Outcome of evaluating an expression in the running game (issue #677).

    Evaluation runs in-game via the runtime probe's `Expression` path (the editor
    debugger's paused-frame eval is not exposed to plugins on Godot 4.7), so it is
    not frame-scoped. `error` carries a parse/execute failure message (empty on
    success) — a null `value` with `evaluated=True` and an `error` is a real
    failure, never a silent null.
    """

    expression: str = ""
    value: Any = None
    evaluated: bool = False
    error: str = ""


class FrameVarsResult(BaseModel):
    """Outcome of requesting variables at a given stack frame."""

    frame: int = 0
    locals: list[dict[str, Any]] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    globals: list[dict[str, Any]] = Field(default_factory=list)
