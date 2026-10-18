"""Debugger breakpoint control tools (issue #110, Tier 1 + Tier 2).

Control breakpoints and step execution in a running editor play session via the
debugger session. Requires a play session; the game must be connected to the
editor debugger.

Tier 1: set_breakpoint, remove_breakpoint, clear_breakpoints, force_break
Tier 2: step_into, step_over, step_out, continue_execution

Gated in the ``debugger`` toolset.
"""

from __future__ import annotations

import asyncio
import uuid

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import DEBUGGER_TAG
from mcp_server.constraints import TimeoutMs
from mcp_server.defaults import DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS
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
from mcp_server.paths import ResPath
from mcp_server.safety import RUNTIME, RUNTIME_EXECUTES_CODE
from mcp_server.tools._route import poll_ready, route

DEBUGGER = {DEBUGGER_TAG}

# force_break lands a frame or two after the probe services the flag; poll the
# break-state read before answering (import_asset-style, no editor-side sleep).
_BREAK_POLL_INTERVAL_S = 0.1
_BREAK_POLL_TIMEOUT_S = 2.0


def register_debugger(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the debugger breakpoint and step control tools."""

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def set_breakpoint(path: ResPath, line: int) -> BreakpointResult:
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
    async def remove_breakpoint(path: ResPath, line: int) -> BreakpointResult:
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
        Requires a play session with the Godot Editor MCP runtime probe autoload.

        WHEN TO USE: You need the game to pause RIGHT NOW so you can inspect
        stack frames, step through code, or evaluate expressions (e.g., the player
        just hit an enemy and you want to see local variables).
        WHEN NOT TO USE: You want the game to pause later when a specific line
        runs — use set_breakpoint(path, line) instead. force_break pauses
        immediately, which may land in an unrelated function.

        Returns ``breaked``: whether the game actually entered the break loop
        (polled for up to ~2s). ``force_break_sent`` with ``breaked=False``
        means the break did NOT land — do not trust stack/input tools until
        ``godot_runtime_is_playing`` shows ``paused=true``.
        """
        await route(bridge, "cmd_force_break", {})
        # The probe services the break flag on its next frame — poll the
        # break-state read (import_asset-style) so the result is honest (#411).
        breaked = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _BREAK_POLL_TIMEOUT_S
        while True:
            state = await bridge.send("cmd_get_debug_break_state", {})
            if state.ok and (state.result or {}).get("breaked"):
                breaked = True
                break
            if loop.time() >= deadline:
                break
            await asyncio.sleep(_BREAK_POLL_INTERVAL_S)
        return ForceBreakResult(force_break_sent=True, breaked=breaked)

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

        NOT AVAILABLE on Godot 4.7 (issue #677): the paused-frame call stack is
        delivered by the editor's internal ScriptEditorDebugger over the debugger
        protocol, which is not exposed to editor debugger plugins — so this returns
        a structured ``UNSUPPORTED`` error rather than a silent empty list.
        """
        return StackFramesResult(**await route(bridge, "cmd_get_stack_frames", {}))

    @mcp.tool(meta=RUNTIME_EXECUTES_CODE, tags=DEBUGGER)
    async def evaluate_expression(
        expression: str,
        timeout_ms: TimeoutMs = DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS,
    ) -> EvaluationResult:
        """Evaluate a GDScript ``expression`` in the *running game* and return its
        value. Requires a play session with the runtime probe. ``error`` is set (and
        ``value`` null) on a parse/execute failure — never a silent null.

        Issue #677: evaluation runs in-game via the probe's ``Expression`` path, so
        it is evaluated in the game's global scope (base instance = the scene root);
        it is **not** frame-scoped/paused-frame eval (Godot 4.7 does not expose the
        paused-frame evaluator to editor debugger plugins).

        Runs arbitrary code in the game process, so it is approval-gated (issue
        #638): a configured approval webhook / guard must approve it first.
        """
        params = {"expression": expression, "request_id": uuid.uuid4().hex}
        result = await poll_ready(bridge, "cmd_evaluate_expression", params, timeout_ms)
        return EvaluationResult(**result)

    @mcp.tool(meta=RUNTIME, tags=DEBUGGER)
    async def get_frame_variables() -> FrameVarsResult:
        """Get local, member, and global variables for the paused frame.

        NOT AVAILABLE on Godot 4.7 (issue #677): paused-frame variables are served
        by the editor's internal ScriptEditorDebugger, not exposed to editor debugger
        plugins — this returns a structured ``UNSUPPORTED`` error.
        """
        return FrameVarsResult(**await route(bridge, "cmd_get_frame_variables", {}))
