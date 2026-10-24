"""Consent-token enforcement at the tool boundary (issue #759).

``describe_tool`` mints a token over the exact ``(tool, canonical args)``. This
middleware:

- advertises an optional ``consent`` argument on every destructive tool's input
  schema,
- strips it before FastMCP validates the tool's real parameters,
- verifies it (HMAC + expiry + replay) and injects ``confirm=True`` on success,
- requires a token for destructive calls when approval is configured, and
- raises ``CONSENT_MISMATCH`` with a ``next_call`` to ``describe_tool`` on any
  mismatch.

Without approval configured, ``confirm=True`` keeps working as the accident
guard; a valid consent token also works. Dry-runs never need consent.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware

from mcp_server.agent_errors import AgentToolError
from mcp_server.consent import APPROVAL_PRECLEARED, ConsentError, ConsentManager
from mcp_server.models.envelope import NextCall
from mcp_server.safety import ApprovalGate
from mcp_server.tools.consent import DESCRIBE_TOOL


async def apply_consent_schema(mcp: Any) -> None:
    """Advertise the optional ``consent`` argument on destructive tools."""
    for tool in await mcp.local_provider.list_tools():
        if (getattr(tool, "meta", None) or {}).get("safety_class") != "destructive":
            continue
        schema = getattr(tool, "parameters", None)
        if not isinstance(schema, dict):
            continue
        props = schema.setdefault("properties", {})
        props.setdefault(
            "consent",
            {
                "type": "string",
                "description": (
                    "Consent token from godot_describe_tool for these exact args "
                    "(required when approval is configured)."
                ),
            },
        )


class ConsentMiddleware(Middleware):
    """Verify consent tokens for destructive tools (#759)."""

    def __init__(self, consent: ConsentManager, approval: ApprovalGate) -> None:
        self._consent = consent
        self._approval = approval

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        name = getattr(getattr(context, "message", None), "name", "")
        tool = await self._get_tool(context)
        if tool is None or (getattr(tool, "meta", None) or {}).get("safety_class") != "destructive":
            return await call_next(context)

        args = dict(getattr(context.message, "arguments", None) or {})
        if args.get("dry_run"):
            # Previews never mutate; the approval gate short-circuits them too.
            args.pop("consent", None)
            context.message.arguments = args
            return await call_next(context)

        token = args.pop("consent", None)
        # The webhook path needs a token bound to the approved args. The guard
        # pattern is itself the approval at call time, so it stays token-optional.
        approval_required = bool(self._approval.webhook_url)
        if token:
            try:
                self._consent.verify(name, args, str(token))
            except ConsentError as exc:
                raise self._consent_error(name, args, exc.hint) from exc
            if self._has_confirm(tool):
                args["confirm"] = True
            context.message.arguments = args
            # A webhook-minted token already carries human approval for these
            # exact args; don't ask the same human twice.
            if self._approval.webhook_url:
                reset = APPROVAL_PRECLEARED.set(True)
                try:
                    return await call_next(context)
                finally:
                    APPROVAL_PRECLEARED.reset(reset)
            return await call_next(context)

        if approval_required:
            raise self._consent_error(
                name,
                args,
                "This destructive call requires a consent token because approval is "
                "configured. Call describe_tool with the exact args first.",
            )
        return await call_next(context)

    def _consent_error(
        self, name: str, args: dict[str, Any], hint: str
    ) -> AgentToolError:
        clean = {k: v for k, v in args.items() if k not in ("consent", "confirm")}
        return AgentToolError(
            "CONSENT_MISMATCH",
            hint,
            required="consent",
            next_call=NextCall(
                tool=DESCRIBE_TOOL,
                args={"tool": name, "args": clean},
                reason="mint a consent token for these exact arguments",
            ),
        )

    @staticmethod
    async def _get_tool(context: Any) -> Any:
        try:
            return await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        except Exception:
            return None

    @staticmethod
    def _has_confirm(tool: Any) -> bool:
        props = ((getattr(tool, "parameters", None) or {}).get("properties") or {})
        return "confirm" in props
