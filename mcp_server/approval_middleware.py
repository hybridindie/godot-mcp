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
``request_state``) and works on the sessionless protocol Godot Editor MCP uses by
design (see ``.claude/rules/async-patterns.md``).

Issue #876 binds the approval to the call it approved: ``request_state`` is
sealed with an HMAC-SHA256 under a per-process key, and the continuation round
is denied unless the state is present, verifies, and names the same tool and
canonical params as the call being continued. Without that, one "approve"
answer authorized any arguments the client chose to send with it. The state
also seals an ``exp`` and a ``nonce`` (mirroring ``consent.ConsentManager``),
so an approval expires and can be spent only once.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import InputRequiredToolResult
from mcp.types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult

from mcp_server.consent import APPROVAL_PRECLEARED, canonical_args
from mcp_server.models.envelope import ErrorCode
from mcp_server.safety import ApprovalGate, PreconditionError, approval_gated
from mcp_server.subcommand_policy import effective_safety_class

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


# The field in ``request_state`` holding the HMAC over the other fields.
_SIG_KEY = "sig"

# A well-formed ``sig``: SHA-256 hexdigest. Checked before any comparison so a
# client-controlled value (non-ASCII, lone surrogate) can only fail closed.
_SIG_RE = re.compile(r"[0-9a-f]{64}")

# How long an approval may sit before its continuation is refused (matches the
# consent token TTL in ``consent.py``).
_DEFAULT_TTL_SECONDS = 120.0


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sign(key: bytes, payload: dict[str, Any]) -> str:
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def seal_request_state(key: bytes, payload: dict[str, Any]) -> str:
    """Seal ``payload`` as JSON plus an HMAC-SHA256 ``sig`` over its canonical form.

    The state stays readable JSON (clients may show it), but any edit to the
    tool, class or params breaks the signature.
    """
    normalized: dict[str, Any] = json.loads(_canonical(payload))
    return json.dumps({**normalized, _SIG_KEY: _sign(key, normalized)}, sort_keys=True)


def unseal_request_state(key: bytes, state: str | None) -> dict[str, Any] | None:
    """Return the sealed payload, or ``None`` when absent, malformed or tampered."""
    if not state or not isinstance(state, str):
        return None
    try:
        payload = json.loads(state)
    except (ValueError, RecursionError):
        # RecursionError: a deeply nested client-supplied state.
        return None
    if not isinstance(payload, dict):
        return None
    signature = payload.pop(_SIG_KEY, None)
    if not isinstance(signature, str) or not _SIG_RE.fullmatch(signature):
        return None
    if not hmac.compare_digest(_sign(key, payload), signature):
        return None
    return payload


def _build_input_required(
    tool_name: str,
    safety_class: str,
    params: dict[str, Any],
    *,
    key: bytes,
    expires_at: float,
) -> InputRequiredToolResult:
    """Build the guard's first-round result: an elicitation asking the client
    to approve or deny the call. The tool name + params + safety_class, an
    expiry and a fresh nonce are sealed into ``request_state`` under ``key`` so
    the second round can check the continuation is the call that was approved,
    still fresh and not yet spent, without server-side state beyond used nonces.
    """
    message = f"Approve {tool_name} ({safety_class})? params={json.dumps(params, default=str)}"
    request_state = seal_request_state(
        key,
        {
            "tool": tool_name,
            "safety_class": safety_class,
            "params": params,
            "exp": expires_at,
            "nonce": secrets.token_urlsafe(12),
        },
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

    # Cap the spent-nonce set so a flood of approvals cannot grow it without
    # bound; expired entries are pruned on every accepted continuation.
    _MAX_USED = 10_000

    def __init__(
        self,
        approval: ApprovalGate,
        *,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._approval = approval
        # Per-process key: a restart invalidates in-flight approvals, which
        # fails closed (the client is asked again).
        self._state_key = secrets.token_bytes(32)
        self._ttl = ttl_seconds
        self._clock = clock
        # nonce -> exp of each approval already spent (replay prevention).
        self._used: dict[str, float] = {}

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        if APPROVAL_PRECLEARED.get():
            # A consent token minted after this exact call's webhook approval
            # already carries the human's decision (#759).
            return await call_next(context)
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
            # Fail-open here (not fail-closed) so the agent can still reach core
            # recovery tools (godot_list_toolsets, godot_enable_toolset) when an
            # internal lookup error occurs. The destructive ``confirm`` gate
            # lives in each tool's body via ``require_confirmation`` — that is
            # the primary security gate and runs regardless of this lookup, so
            # fail-open here does not leave destructive tools unprotected. The
            # toolset middleware fails open for the same reason (issue #369).
            logger.error(
                "unexpected error looking up tool %r; allowing call (approval "
                "gate fails open — the tool's own confirm gate still protects "
                "destructive tools)",
                context.message.name,
                exc_info=True,
            )
            return await call_next(context)
        if tool is None:
            return await call_next(context)
        # #634: a run_commands batch is approved at the severity of its most
        # dangerous entry (a batch containing a delete is destructive), not the
        # outer tool's mutating class. Every other tool keeps its own class.
        try:
            safety_class: str = await effective_safety_class(
                context.fastmcp_context.fastmcp, tool, args
            )
        except Exception:
            safety_class = (tool.meta or {}).get("safety_class") or ""
        # Gate by class, plus RUNTIME tools that write disk or execute code
        # (writes_disk/executes_code meta, issue #638).
        if not approval_gated(safety_class, tool.meta):
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
                context.message.name,
                safety_class,
                context.message.arguments or {},
                key=self._state_key,
                expires_at=self._clock() + self._ttl,
            )

        # Continuation round: the client has answered. Read the approve field.
        answer = responses.get(APPROVE_KEY)
        approved = False
        if answer is not None and getattr(answer, "action", None) == "accept":
            content = getattr(answer, "content", None) or {}
            approved = bool(content.get("approve", False))

        # #876: the answer only counts for the exact call it was asked about.
        if approved and not self._state_matches(context, fctx, safety_class):
            raise PreconditionError(
                f"'{context.message.name}' continuation does not match the approved "
                "call (missing, tampered, expired, already used, or different "
                "tool/params/safety class). Call the tool "
                "again without input responses to request a fresh approval.",
                required="human_approval",
                error=ErrorCode.APPROVAL_DENIED,
            ).as_tool_error()

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

    def _state_matches(self, context: MiddlewareContext, fctx: Any, safety_class: str) -> bool:
        """True when the sealed ``request_state`` names this tool, params and
        safety class, has not expired, and its nonce is unspent. Spends the
        nonce on success, so the same approval cannot run the tool twice.
        """
        payload = unseal_request_state(self._state_key, getattr(fctx, "request_state", None))
        if payload is None:
            return False
        params = payload.get("params")
        if payload.get("tool") != context.message.name or not isinstance(params, dict):
            return False
        if payload.get("safety_class") != safety_class:
            return False
        if not hmac.compare_digest(
            canonical_args(params), canonical_args(context.message.arguments or {})
        ):
            return False
        exp = payload.get("exp")
        nonce = payload.get("nonce")
        # bool is an int subclass; a sealed True is not an expiry.
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            return False
        if not isinstance(nonce, str) or not nonce:
            return False
        now = self._clock()
        if exp < now or nonce in self._used:
            return False
        self._used[nonce] = float(exp)
        self._prune(now)
        while len(self._used) > self._MAX_USED:
            # Drop the oldest-inserted entry; it expires soonest.
            self._used.pop(next(iter(self._used)))
        return True

    def _prune(self, now: float) -> None:
        """Drop spent nonces whose approval has expired (it can't verify anyway)."""
        for nonce in [n for n, exp in self._used.items() if exp < now]:
            self._used.pop(nonce, None)
