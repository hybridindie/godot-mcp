"""Bridge → tool routing helper (issue #5).

Keeps tool handlers thin (delegation only, per .claude/rules/architecture.md): send
a command, return the result dict on success, or raise a ``ToolError`` carrying the
structured ``error: hint`` on failure so the agent gets an actionable message
instead of a stack trace.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge


async def route(
    bridge: Bridge, command: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a command over the bridge; return its result or raise a structured error."""
    response = await bridge.send(command, params or {})
    if not response.ok:
        detail = f"{response.error}: {response.hint}" if response.hint else str(response.error)
        raise ToolError(detail)
    return response.result or {}
