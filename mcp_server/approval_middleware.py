"""Approval-gate middleware (issue #330, extended by #346).

Centralizes the webhook ``ApprovalGate`` at the ``tools/call`` boundary so the
``approval`` parameter no longer threads through ~6 register modules. The
middleware inspects the called tool's ``safety_class`` meta (already set on
every tool via ``safety.py``) and routes ``destructive`` calls through
``approval.require(...)`` before the tool runs. ``dry_run`` short-circuits the
gate (a preview never needs approval).

The ``confirm`` bool check (``require_confirmation``) stays in each tool's
body — it's the tool's own schema-level gate, not the webhook gate.

Issue #346 adds the **guard pattern**: when ``require_approval`` is set and
no webhook is configured, a ``mutating``/``destructive`` tool returns an
``InputRequiredResult`` (an elicitation the client fulfils and re-calls) on
its first round, and the second round inspects the answer in
``ctx.input_responses`` to either run the tool or deny. This is durable (no
server-side state — the tool name + params + safety_class round-trip through
``request_state``) and works on the sessionless protocol godot-mcp uses by
design (see ``.opencode/rules/async-patterns.md``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import InputRequiredToolResult
from mcp.types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult

from mcp_server.models.envelope import ErrorCode
from mcp_server.safety import ApprovalGate, PreconditionError, SafetyClass

logger = logging.getLogger(__name__)

# The elicitation key the guard uses for the approve/deny ask. The client's
# answer arrives in ``ctx.input_responses[APPROVE_KEY]`` on the next round.
APPROVE_KEY = "approve"

# JSON Schema for the elicitation: a single boolean "approve" field. The
# client renders this as a yes/no form (or, for a programmatic handler, a
# typed ElicitResult(approve=bool)).
_APPROVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"approve": {"type": "boolean", "title": "Approve"}},
    "required": ["approve"],
}


def _is_gated_safety_class(value: str) -> bool:
    """mutating and destructive tools are gated; read_only and runtime are not."""
    return value in (SafetyClass.MUTATING.value, SafetyClass.DESTRUCTIVE.value)


def _build_input_required(
    tool_name: str, safety_class: str, params: dict[str, Any]
) -> InputRequiredToolResult:
    """Build the guard's first-round result: an elicitation asking the client
    to approve or deny the call. The tool name + params + safety_class are
    sealed into ``request_state`` so the second round can re-evaluate without
    server-side state.
    """
    message = f"Approve {tool_name} ({safety_class})? params={json.dumps(params, default=str)}"
    request_state = json.dumps(
        {"tool": tool_name, "safety_class": safety_class, "params": params},
        default=str,
    )
    elicitation = ElicitRequest(
        method="elicitation/create",
        params=ElicitRequestFormParams(
            mode="form", message=message, requested_schema=_APPROVE_SCHEMA
        ),
    )
    return InputRequiredToolResult(
        InputRequiredResult(
            input_requests={APPROVE_KEY: elicitation},
            request_state=request_state,
        )
    )


class ApprovalMiddleware(Middleware):
    """Route ``destructive``/``mutating`` tool calls through approval.

    Three modes, in precedence order:

    1. ``dry_run=True`` → short-circuit (previews never need approval).
    2. Webhook configured → existing behavior: ``ApprovalGate.require()`` POSTs
       and raises ``ToolError`` on denial.
    3. ``require_approval=True`` + no webhook → guard pattern: return an
       ``InputRequiredResult`` on the first round; on the second round, read
       the client's answer from ``ctx.input_responses`` and either run the
       tool (approved) or raise ``PreconditionError(APPROVAL_DENIED)``
       (denied/declined/cancelled).

    No-op when none of the above apply (the gate auto-approves).
    """

    def __init__(self, approval: ApprovalGate) -> None:
        self._approval = approval

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        args = context.message.arguments or {}
        if args.get("dry_run"):
            return await call_next(context)
        if not context.fastmcp_context:
            return await call_next(context)
        try:
            tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        except ToolError:
            return await call_next(context)
        except Exception:
            logger.warning(
                "unexpected error looking up tool %r; skipping approval gate",
                context.message.name,
                exc_info=True,
            )
            return await call_next(context)
        if tool is None:
            return await call_next(context)
        safety_class: str = (tool.meta or {}).get("safety_class") or ""
        if not _is_gated_safety_class(safety_class):
            return await call_next(context)

        # Webhook path (issue #153): POST + raise on denial. The webhook is
        # authoritative when configured; the guard pattern is the no-webhook
        # fallback for durable, stateless approval.
        if self._approval.webhook_url:
            try:
                await self._approval.require(context.message.name, safety_class, args)
            except PreconditionError as exc:
                raise exc.as_tool_error() from exc
            return await call_next(context)

        # Guard pattern (issue #346): opt-in, no webhook. The first round asks
        # the client; the second round reads the answer.
        if self._approval.require_approval:
            return await self._guard_round(context, call_next, safety_class)

        return await call_next(context)

    async def _guard_round(
        self,
        context: MiddlewareContext,
        call_next: Any,
        safety_class: str,
    ) -> Any:
        """One round of the guard pattern. First round → ask. Later rounds →
        inspect the answer and run the tool or deny.
        """
        fctx = context.fastmcp_context
        assert fctx is not None  # narrowed by the caller
        responses = fctx.input_responses

        # First round: no answers yet → ask the client to approve.
        if responses is None:
            return _build_input_required(
                context.message.name, safety_class, context.message.arguments or {}
            )

        # Continuation round: the client has answered. Read the approve field.
        answer = responses.get(APPROVE_KEY)
        approved = False
        if answer is not None and getattr(answer, "action", None) == "accept":
            content = getattr(answer, "content", None) or {}
            approved = bool(content.get("approve", False))

        if not approved:
            # Decline, cancel, or an explicit "approve: false" all deny. The
            # error is a structured PreconditionError → ToolError so the agent
            # gets an actionable message instead of a stack trace.
            raise PreconditionError(
                f"'{context.message.name}' was denied by the human approver.",
                required="human_approval",
                error=ErrorCode.APPROVAL_DENIED,
            ).as_tool_error()

        # Approved — run the tool. The tool's own ``confirm``/precondition
        # gates still run in its body (the guard does not duplicate them).
        return await call_next(context)
