"""Bridge → tool routing helper (issue #5).

Keeps tool handlers thin (delegation only, per .claude/rules/architecture.md): send
a command, return the result dict on success, or raise a structured ``ToolError`` on
failure so the agent gets an actionable message instead of a stack trace. When the
addon returns a precondition-style envelope (carrying ``required``), that field is
included in the error text so the agent knows what to satisfy — regardless of whether
the calling tool is decorated with ``@enforce_preconditions`` (read-only tools are not).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge


async def route(
    bridge: Bridge, command: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a command over the bridge; return its result or raise a structured error.

    On failure raises a ``ToolError`` of the form ``"<error>: <hint> [required=<x>]"``
    (the ``[required=...]`` suffix only when the envelope carries one), matching the
    shape ``PreconditionError.as_tool_error()`` produces — so a precondition surfaced
    by the addon is actionable even from an undecorated read-only tool.
    """
    response = await bridge.send(command, params or {})
    if not response.ok:
        detail = f"{response.error}: {response.hint}" if response.hint else str(response.error)
        if response.required:
            detail = f"{detail} [required={response.required}]"
        raise ToolError(detail)
    return response.result or {}


async def poll_ready(
    bridge: Bridge, command: str, params: dict[str, Any], timeout_ms: int
) -> dict[str, Any]:
    """Poll a poll-and-cache command until its result is ``ready`` or ``timeout_ms``
    elapses (whichever first), returning the last result. Uses an event-loop deadline so
    the wall-clock bound holds even for small timeouts and accounts for round-trip time.
    Always makes at least one attempt.
    """
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    result = await route(bridge, command, params)
    while not result.get("ready"):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(0.1, remaining))
        result = await route(bridge, command, params)
    return result
