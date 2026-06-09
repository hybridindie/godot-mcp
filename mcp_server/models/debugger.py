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


class StepResult(BaseModel):
    """Outcome of a debugger step command."""

    stepped: bool = False


class ContinueResult(BaseModel):
    """Outcome of resuming execution after a breakpoint."""

    running: bool = False


class StackFramesResult(BaseModel):
    """Outcome of requesting the current call stack."""

    frames: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    """Outcome of evaluating an expression in a paused frame."""

    expression: str = ""
    value: Any = None


class FrameVarsResult(BaseModel):
    """Outcome of requesting variables at a given stack frame."""

    frame: int = 0
    locals: list[dict[str, Any]] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    globals: list[dict[str, Any]] = Field(default_factory=list)
