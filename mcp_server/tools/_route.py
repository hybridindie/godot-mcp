"""Bridge → tool routing helper (issue #5).

Keeps tool handlers thin (delegation only, per .claude/rules/architecture.md): send
a command, return the result dict on success, or raise a structured error on failure
so the agent gets an actionable message instead of a stack trace. When the addon
returns a precondition-style envelope (carrying ``required``), the field is preserved
via :class:`PreconditionError` so the agent knows what to satisfy.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.safety import PreconditionError


async def route(
    bridge: Bridge, command: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a command over the bridge; return its result or raise a structured error.

    A failure that carries a ``required`` field is re-raised as a
    :class:`PreconditionError` (preserving ``error``/``hint``/``required``); the
    ``@enforce_preconditions`` decorator turns that into a structured ``ToolError``.
    Other failures raise a plain ``ToolError`` with ``error: hint``.
    """
    response = await bridge.send(command, params or {})
    if not response.ok:
        if response.required:
            raise PreconditionError(
                response.hint or "A precondition check failed.",
                required=response.required,
                error=response.error or "INTERNAL_ERROR",
            )
        detail = f"{response.error}: {response.hint}" if response.hint else str(response.error)
        raise ToolError(detail)
    return response.result or {}
