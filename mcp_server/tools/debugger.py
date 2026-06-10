"""Debugger breakpoint control tools (issue #110, Tier 1 + Tier 2).

Control breakpoints and step execution in a running editor play session via the
debugger session. Requires a play session; the game must be connected to the
editor debugger.

Tier 1: set_breakpoint, remove_breakpoint, clear_breakpoints, force_break
Tier 2: step_into, step_over, step_out, continue_execution

Gated in the ``debugger`` toolset.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import DEBUGGER_TAG
from mcp_server.models.debugger import (
    BreakpointResult,
    ClearBreakpointsResult,
    ContinueResult,
    EvaluationResult,
    ForceBreakResult,
    FrameVarsResult,
    StackFramesResult,
    StepResult,
)
from mcp_server.safety import RUNTIME
from mcp_server.tools._route import route

DEBUGGER = {DEBUGGER_TAG}


def register_debugger(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the debugger breakpoint and step control tools."""

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def set_breakpoint(path: str, line: int) -> BreakpointResult:
        """Set a breakpoint at ``line`` in ``path`` (a ``res://`` script path).
        The game must be running from the editor so the debugger session is active.

        WHEN TO USE: You want the game to pause automatically when a specific
        line of code is reached (e.g., to inspect state at the moment of impact).
        WHEN NOT TO USE: You need the game to pause RIGHT NOW — use force_break()
        instead. Setting a breakpoint only triggers when that line executes.
        """
        params = {"path": path, "line": line}
        return BreakpointResult(**await route(bridge, "cmd_set_breakpoint", params))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def remove_breakpoint(path: str, line: int) -> BreakpointResult:
        """Remove a previously-set breakpoint at ``line`` in ``path``."""
        params = {"path": path, "line": line}
        return BreakpointResult(**await route(bridge, "cmd_remove_breakpoint", params))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def clear_breakpoints() -> ClearBreakpointsResult:
        """Clear every breakpoint in the current debug session (editor + game side)."""
        return ClearBreakpointsResult(**await route(bridge, "cmd_clear_breakpoints", {}))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def force_break() -> ForceBreakResult:
        """Trigger an immediate break in the running game via the runtime probe.
        Requires a play session with the godot-mcp runtime probe autoload.

        WHEN TO USE: You need the game to pause RIGHT NOW so you can inspect
        stack frames, step through code, or evaluate expressions (e.g., the player
        just hit an enemy and you want to see local variables).
        WHEN NOT TO USE: You want the game to pause later when a specific line
        runs — use set_breakpoint(path, line) instead. force_break pauses
        immediately, which may land in an unrelated function.
        """
        return ForceBreakResult(**await route(bridge, "cmd_force_break", {}))

    # Tier 2: step control --------------------------------------------------

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def step_into() -> StepResult:
        """Step into the next line of GDScript execution. The game must be paused
        (e.g. at a breakpoint or after force_break)."""
        return StepResult(**await route(bridge, "cmd_step_into"))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def step_over() -> StepResult:
        """Step over the next line of GDScript execution, treating function calls
        as a single step. The game must be paused."""
        return StepResult(**await route(bridge, "cmd_step_over"))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def step_out() -> StepResult:
        """Step out of the current function, pausing at the caller's next line
        of GDScript execution. The game must be paused."""
        return StepResult(**await route(bridge, "cmd_step_out"))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def continue_execution() -> ContinueResult:
        """Resume GDScript execution after a breakpoint or forced break.
        The game must be paused.
        """
        return ContinueResult(**await route(bridge, "cmd_continue_execution"))

    # Tier 2: stack / eval --------------------------------------------------

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def get_stack_frames() -> StackFramesResult:
        """Get the current GDScript call stack while the game is paused.
        Returns a list of frames, each with ``file``, ``line``, and ``func``.
        """
        return StackFramesResult(**await route(bridge, "cmd_get_stack_frames"))

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def evaluate_expression(expression: str, frame: int = 0) -> EvaluationResult:
        """Evaluate a GDScript expression in the context of the given ``frame``.
        ``frame`` 0 is the top of the stack (the currently executing function).
        The game must be paused.
        """
        return EvaluationResult(
            **await route(
                bridge,
                "cmd_evaluate_expression",
                {"expression": expression, "frame": frame},
            )
        )

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def get_frame_variables(frame: int = 0) -> FrameVarsResult:
        """Get local, member, and global variables for ``frame``.
        Returns three arrays under ``locals``, ``members``, and ``globals``.
        The game must be paused.
        """
        return FrameVarsResult(
            **await route(bridge, "cmd_get_frame_variables", {"frame": frame})
        )
