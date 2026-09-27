"""Result-model validation middleware (issue #567).

When a tool builds its typed result from an addon payload — ``ClassInfo(**result)``,
``MonitorResult(**…)``, ``run_or_preview(...)``, and every other ``Model(**payload)``
call site — a payload that doesn't match the model raises pydantic's
``ValidationError`` out of the tool body. FastMCP mapped that to JSON-RPC
``-32602 Invalid request parameters``, which tells the agent *its own arguments*
were wrong when the real bug is "the addon sent the wrong shape" — and carries
none of pydantic's per-field detail on the wire.

This middleware wraps ``on_call_tool``: a ``pydantic`` ``ValidationError`` escaping
a tool body is re-raised as a ``ToolError`` whose text carries ``INTERNAL_ERROR``,
the model name, per-field paths/messages, and truncated inputs, framed so the
agent can tell "addon payload mismatch" apart from "I sent bad params".

Request-side parameter validation is deliberately untouched: FastMCP raises its
own ``fastmcp.exceptions.ValidationError`` for bad *arguments* (already a
detailed ToolError on the wire), and that type is unrelated to pydantic's — so
``-32602`` stays reserved for genuinely invalid request parameters.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 100
_MAX_ERRORS = 8
_MAX_VALUE_CHARS = 40


def _truncate(value: Any, limit: int = _MAX_VALUE_CHARS) -> str:
    """Compact repr of an offending input, hard-capped so a huge payload
    can't flood the wire."""
    text = repr(value)
    if len(text) > limit:
        text = text[:limit] + f"… (+{len(text) - limit} chars)"
    return text


def format_result_validation_error(tool: str, model: str, exc: ValidationError) -> str:
    """Render a result-model ``ValidationError`` as an INTERNAL_ERROR text:
    tool, result model, per-field paths/messages (capped), truncated inputs."""
    lines = [
        f"INTERNAL_ERROR: tool {tool!r} built a result that failed its "
        f"{model} model validation — the addon payload didn't match the "
        f"expected shape (your arguments were accepted; this is not a "
        f"parameter problem).",
    ]
    errors = exc.errors()[:_MAX_ERRORS]
    hidden = len(exc.errors()) - len(errors)
    for err in errors:
        loc = ".".join(str(part) for part in err.get("loc", ())) or "<root>"
        msg = err.get("msg", "?")
        err_type = err.get("type", "?")
        line = f"  - {loc}: {msg} [type={err_type}]"
        if "input" in err:
            line += f" input={_truncate(err['input'])}"
        lines.append(line)
    if hidden > 0:
        lines.append(f"  … and {hidden} more validation error(s)")
    lines.append(
        "  Hint: the addon's response shape drifted from the model — check the "
        "addon version vs the server, and report the mismatch."
    )
    return "\n".join(lines)


class ResultValidationMiddleware(Middleware):
    """Convert result-side pydantic ``ValidationError`` into a structured
    ``ToolError`` (see module docstring for the #567 rationale)."""

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        try:
            return await call_next(context)
        except ValidationError as exc:
            # pydantic's ValidationError only — FastMCP's request-side
            # fastmcp.exceptions.ValidationError is a different, unrelated type
            # and must keep its own detailed request-validation error (#567).
            tool = getattr(getattr(context, "message", None), "name", "<unknown>")
            model = _model_name(exc)
            text = format_result_validation_error(tool, model, exc)
            logger.error(
                "result-model validation failed for tool %s (model %s)",
                tool,
                model,
                exc_info=True,
            )
            raise ToolError(text) from exc
        except Exception:
            raise


def _model_name(exc: ValidationError) -> str:
    """Best-effort name of the model that failed, from the error title."""
    title = getattr(exc, "title", "") or ""
    return title.split()[0] if title else "<unknown model>"


__all__ = [
    "ResultValidationMiddleware",
    "format_result_validation_error",
    "BaseModel",  # re-export convenience for tests
]