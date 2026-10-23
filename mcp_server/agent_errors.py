"""Structured, recoverable tool errors (issue #757).

A plain ``ToolError`` is text on the wire. This module adds an ``AgentToolError``
that keeps the same text (so clients and existing tests that match the message
are unchanged) while carrying the machine-readable fields the client sees in the
error result's ``structuredContent``: ``error``, ``hint``, ``required`` and
``next_call`` (a fully-formed call the client can send as-is).

The middleware in ``agent_error_middleware.py`` converts it to an
``is_error=True`` ``ToolResult``; without that middleware it still behaves like
any other ``ToolError``.
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from mcp_server.models.envelope import ErrorCode, NextCall


class AgentToolError(ToolError):
    """A ``ToolError`` with structured recovery data (#757)."""

    def __init__(
        self,
        code: ErrorCode | str,
        hint: str,
        *,
        required: str | None = None,
        next_call: NextCall | dict[str, Any] | None = None,
    ) -> None:
        self.code = str(code.value if isinstance(code, ErrorCode) else code)
        self.hint = hint
        self.required = required
        if isinstance(next_call, dict):
            next_call = NextCall(**next_call)
        self.next_call = next_call
        text = f"{self.code}: {hint}"
        if required:
            text += f" [required={required}]"
        super().__init__(text)

    def structured_payload(self) -> dict[str, Any]:
        """The ``structuredContent`` shape for the client (#757)."""
        payload: dict[str, Any] = {
            "ok": False,
            "error": self.code,
            "hint": self.hint,
        }
        if self.required:
            payload["required"] = self.required
        if self.next_call is not None:
            payload["next_call"] = self.next_call.model_dump(exclude_none=True)
        return payload
