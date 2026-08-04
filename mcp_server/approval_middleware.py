"""Approval-gate middleware (issue #330).

Centralizes the webhook ``ApprovalGate`` at the ``tools/call`` boundary so the
``approval`` parameter no longer threads through ~6 register modules. The
middleware inspects the called tool's ``safety_class`` meta (already set on
every tool via ``safety.py``) and routes ``destructive`` calls through
``approval.require(...)`` before the tool runs. ``dry_run`` short-circuits the
gate (a preview never needs approval).

The ``confirm`` bool check (``require_confirmation``) stays in each tool's
body — it's the tool's own schema-level gate, not the webhook gate.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_server.safety import ApprovalGate, PreconditionError, SafetyClass

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ApprovalMiddleware(Middleware):
    """Route ``destructive`` tool calls through the webhook ``ApprovalGate``.

    No-op when no webhook is configured (the ``ApprovalGate`` auto-approves).
    ``dry_run=True`` short-circuits: a preview never needs approval.
    """

    def __init__(self, approval: ApprovalGate) -> None:
        self._approval = approval

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: Any
    ) -> Any:
        args = context.message.arguments or {}
        if args.get("dry_run"):
            return await call_next(context)
        if not context.fastmcp_context:
            return await call_next(context)
        try:
            tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        except Exception:
            return await call_next(context)
        if tool is None:
            return await call_next(context)
        safety_class = (tool.meta or {}).get("safety_class")
        if safety_class != SafetyClass.DESTRUCTIVE.value:
            return await call_next(context)
        try:
            await self._approval.require(
                context.message.name, safety_class, args
            )
        except PreconditionError as exc:
            raise exc.as_tool_error() from exc
        return await call_next(context)