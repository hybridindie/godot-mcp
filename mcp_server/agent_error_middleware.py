"""Expose structured recovery data on tool errors (issue #757).

``AgentToolError`` (``mcp_server/agent_errors.py``) carries ``error``/``hint``/
``required``/``next_call``. This middleware turns it into an ``is_error=True``
``ToolResult`` whose ``structuredContent`` holds those fields. The text content
is unchanged, so clients that raise on ``is_error`` (and tests that match the
message) still see the same ``ToolError`` text.

It also maps FastMCP's request-side "unexpected keyword argument" validation
failure to ``UNDECLARED_PARAMETER``: the accepted parameter names are listed and,
when the unknown name is a near-miss, ``next_call`` is the same tool with the
argument renamed. Unknown arguments are never silently dropped.
"""

from __future__ import annotations

import re
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.server.middleware import Middleware
from fastmcp.tools.base import ToolResult
from mcp.types import TextContent
from pydantic import ValidationError as PydanticValidationError

from mcp_server.agent_errors import AgentToolError
from mcp_server.models.envelope import ErrorCode, NextCall
from mcp_server.suggestions import suggest


class AgentErrorMiddleware(Middleware):
    """Turn ``AgentToolError`` / undeclared-argument failures into structured errors."""

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        try:
            return await call_next(context)
        except AgentToolError as exc:
            return _error_result(str(exc), exc.structured_payload())
        except FastMCPValidationError as exc:
            undeclared = _undeclared_arguments(exc)
            if not undeclared:
                raise
            return await _undeclared_result(context, undeclared)
        except ToolError as exc:
            # FastMCP masks a TransformedTool's plain TypeError into a
            # ToolError; recover the unknown-argument case from the text.
            undeclared = _unknown_from_message(str(exc))
            if not undeclared:
                raise
            return await _undeclared_result(context, undeclared)


def _error_result(text: str, payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=payload,
        is_error=True,
    )


async def _undeclared_result(context: Any, undeclared: list[str]) -> ToolResult:
    tool_name = getattr(getattr(context, "message", None), "name", "<unknown>")
    accepted, next_call = await _accepted_and_next(
        context, tool_name, undeclared[0] if len(undeclared) == 1 else ""
    )
    names = ", ".join(f"'{name}'" for name in undeclared)
    hint = (
        f"Unknown parameter{'s' if len(undeclared) > 1 else ''} {names} for "
        f"'{tool_name}'. Accepted parameters: "
        f"{', '.join(accepted) if accepted else '(none)'}."
    )
    error = AgentToolError(
        ErrorCode.UNDECLARED_PARAMETER,
        hint,
        required=undeclared[0],
        next_call=next_call,
    )
    return _error_result(str(error), error.structured_payload())


def _undeclared_arguments(exc: FastMCPValidationError) -> list[str]:
    """Unknown argument names behind a request-side validation failure."""
    pydantic_exc = exc.__cause__
    if not isinstance(pydantic_exc, PydanticValidationError):
        return _unknown_from_message(str(exc))
    names: list[str] = []
    for error in pydantic_exc.errors():
        if error.get("type") not in (
            "unexpected_keyword_argument",
            "extra_forbidden",
        ):
            continue
        loc = error.get("loc") or ()
        if loc:
            names.append(str(loc[0]))
    return names


def _unknown_from_message(text: str) -> list[str]:
    match = re.search(r"unexpected keyword argument\(s\): (.+)", text)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


async def _accepted_and_next(
    context: Any,
    tool_name: str,
    undeclared: str,
) -> tuple[list[str], NextCall | None]:
    """Accepted parameter names for the tool, plus a corrected call when the
    unknown name is a near-miss (the same arguments with the name fixed)."""
    accepted: list[str] = []
    try:
        tool = await context.fastmcp_context.fastmcp.get_tool(tool_name)
        schema = getattr(tool, "parameters", None) or {}
        accepted = list((schema.get("properties") or {}).keys())
    except Exception:
        # Recovery metadata is best-effort; the error itself must still surface.
        return accepted, None
    if not accepted or not undeclared:
        return accepted, None
    closest = suggest(undeclared, accepted, n=1)
    if not closest:
        return accepted, None
    args = dict(getattr(context.message, "arguments", None) or {})
    value = args.pop(undeclared, None)
    if value is None:
        return accepted, None
    args[closest[0]] = value
    return accepted, NextCall(
        tool=tool_name,
        args=args,
        reason=f"rename '{undeclared}' to '{closest[0]}'",
    )
