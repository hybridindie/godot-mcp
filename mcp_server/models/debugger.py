"""Typed results for debugger breakpoint control tools (issue #110, Tier 1 + Tier 2)."""

from __future__ import annotations

from pydantic import BaseModel


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
