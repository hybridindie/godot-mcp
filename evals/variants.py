"""Tool description variant definitions for A/B testing.

Each variant is a mapping from tool name to a description override.
The evaluation harness swaps these into the mcp_server/tools/*.py modules
and measures agent performance.
"""

from __future__ import annotations

# Baseline: current descriptions (used as control)
BASELINE: dict[str, str] = {}


# Concise variant: 50% shorter, action-oriented, no fluff
CONCISE: dict[str, str] = {
    "set_breakpoint": "Set a breakpoint at ``line`` in ``path``. Requires active play session.",
    "remove_breakpoint": "Remove a breakpoint at ``line`` in ``path``.",
    "clear_breakpoints": "Clear all breakpoints in the current debug session.",
    "force_break": "Pause the running game immediately via the runtime probe.",
    "step_into": "Step into the next GDScript line. Game must be paused.",
    "step_over": "Step over the next GDScript line. Game must be paused.",
    "step_out": "Step out of the current function. Game must be paused.",
    "continue_execution": "Resume GDScript execution after a breakpoint.",
    "get_stack_frames": "Get the paused GDScript call stack. Returns ``{frames[]}``.",
    "evaluate_expression": "Evaluate a GDScript expression at ``frame`` (0 = top).",
    "get_frame_variables": (
        "Get locals/members/globals for ``frame``. "
        "Returns ``{locals, members, globals}``."
    ),
}


# Structured variant: explicit WHEN TO USE / PARAMS / RETURNS / EXAMPLE sections
STRUCTURED: dict[str, str] = {
    "set_breakpoint": """Set a breakpoint at ``line`` in ``path``.

WHEN TO USE: Before running a scene to pause execution at a specific script line.
PARAMS: ``path`` (res:// script path), ``line`` (int, 1-based).
RETURNS: ``{breakpoint_set, path, line}``.
EXAMPLE: set_breakpoint("res://player.gd", 42)""",

    "get_stack_frames": """Get the GDScript call stack while the game is paused.

WHEN TO USE: After the game hits a breakpoint or force_break to inspect the call chain.
RETURNS: ``{frames: [{file, line, func}, ...]}``.
NOTE: Returns cached data; the first call after a break may be empty until the async reply arrives.
""",

    "evaluate_expression": """Evaluate a GDScript expression in the context of a paused frame.

WHEN TO USE: To inspect live variables or compute expressions (e.g. ``health * 2``) while paused.
PARAMS: ``expression`` (GDScript string), ``frame`` (0 = top of stack).
RETURNS: ``{expression, value}``.
NOTE: The evaluator requires a valid script instance at the target frame.""",

    "get_frame_variables": """Get local, member, and global variables for a stack frame.

WHEN TO USE: To inspect all scoped variables at a given frame without writing expressions.
PARAMS: ``frame`` (0 = top of stack).
RETURNS: ``{frame, locals: [{name, value}], members: [...], globals: [...]}``.
NOTE: Accumulated from multiple debugger protocol messages;
may need a brief wait after requesting.""",
}


# Agent-optimized variant: includes "call this when..." hints for LLM routing
AGENT_OPTIMIZED: dict[str, str] = {
    "set_breakpoint": (
        "Call this BEFORE running a scene to pause at a specific line. "
        "Set ``path`` (res:// script) and ``line`` (int). Returns confirmation."
    ),
    "remove_breakpoint": (
        "Call this to remove a previously set breakpoint. "
        "Use the same ``path`` and ``line`` as when you set it."
    ),
    "clear_breakpoints": (
        "Call this when you want to start fresh — removes ALL breakpoints. "
        "Safe to call even if none exist."
    ),
    "force_break": (
        "Call this when you need to pause the game NOW "
        "(e.g. to inspect state during a bug). "
        "The game must be running with the MCP runtime probe."
    ),
    "step_into": (
        "Call this when paused to execute the NEXT line, "
        "entering any function calls. "
        "If the next line is a function call, you'll step inside it."
    ),
    "step_over": (
        "Call this when paused to execute the NEXT line, "
        "treating function calls as a single step. "
        "Use this to skip into library code."
    ),
    "step_out": (
        "Call this when paused inside a function to return to "
        "the CALLER's next line. "
        "Use when you've seen enough of the current function."
    ),
    "continue_execution": (
        "Call this when you're done inspecting and want the game to "
        "RESUME running. Opposite of force_break."
    ),
    "get_stack_frames": (
        "Call this immediately AFTER the game pauses (breakpoint or force_break) "
        "to see the call stack. Returns ``{frames: [{file, line, func}]}``. "
        "If empty, wait 0.5s and retry."
    ),
    "evaluate_expression": (
        "Call this when paused to compute a GDScript expression "
        "(e.g. ``player.health > 50``). "
        "Set ``expression`` and optionally ``frame`` (0 = top). "
        "Returns ``{expression, value}``."
    ),
    "get_frame_variables": (
        "Call this when paused to inspect ALL variables at a frame "
        "(locals, members, globals). "
        "Easier than writing expressions. Set ``frame`` (0 = top). "
        "Returns ``{locals, members, globals}``."
    ),
}


ALL_VARIANTS: dict[str, dict[str, str]] = {
    "baseline": BASELINE,
    "concise": CONCISE,
    "structured": STRUCTURED,
    "agent_optimized": AGENT_OPTIMIZED,
}
