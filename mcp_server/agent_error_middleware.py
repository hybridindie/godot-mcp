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

``UndeclaredArgumentMiddleware`` makes the same refusal *before* the gates
that can ask a human (readiness, consent, approval), so a misspelled argument
is refused without an approval prompt for a call that could never run (#877).
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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


class UndeclaredArgumentMiddleware(Middleware):
    """Refuse argument names absent from the tool's input schema, up front.

    Runs ahead of the approval gates so a call that FastMCP would reject during
    validation never reaches a human approver (#877). ``consent`` is always
    allowed: ConsentMiddleware strips it, and dynamic project tools may not
    advertise it. A schema that explicitly admits extra properties is left to
    the tool. Lookup failures fail open; the tool's own validation still runs.
    """

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        undeclared = await _schema_undeclared(context)
        if undeclared:
            return await _undeclared_result(context, undeclared)
        return await call_next(context)


async def _schema_undeclared(context: Any) -> list[str]:
    message: Any = getattr(context, "message", None)
    arguments = getattr(message, "arguments", None)
    if not isinstance(arguments, dict) or not arguments:
        return []
    fastmcp = getattr(getattr(context, "fastmcp_context", None), "fastmcp", None)
    if fastmcp is None:
        # No bound server (a direct/programmatic call): pass through quietly,
        # as the sibling gates do; the tool's own validation still runs.
        return []
    try:
        tool = await fastmcp.get_tool(message.name)
    except ToolError:
        # FastMCP's own no-such-tool signal; its normal not-found path reports it.
        return []
    except Exception:
        # Fail open like the sibling gates (#369): the tool's own validation still
        # runs. Logged at ERROR so a persistent lookup failure is visible.
        logger.error(
            "unexpected error looking up tool %r; skipping the undeclared-argument "
            "check (the tool's own validation still runs)",
            getattr(message, "name", "?"),
            exc_info=True,
        )
        return []
    schema = getattr(tool, "parameters", None)
    if not isinstance(schema, dict) or schema.get("additionalProperties") not in (None, False):
        return []
    declared = schema.get("properties") or {}
    return [name for name in arguments if name != "consent" and name not in declared]


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
