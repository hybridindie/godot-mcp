"""``describe_tool`` — mint a consent token bound to exact destructive args (#759)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError

from mcp_server.agent_errors import AgentToolError
from mcp_server.categories import CORE_TAG
from mcp_server.consent import ConsentError, ConsentManager
from mcp_server.models.consent import ConsentToken
from mcp_server.models.envelope import NextCall
from mcp_server.safety import READ_ONLY, ApprovalGate, PreconditionError

# The public name after the godot_ tool transform (core tools use godot_<action>).
DESCRIBE_TOOL = "godot_describe_tool"


def register_consent_tool(
    mcp: FastMCP, consent: ConsentManager, approval: ApprovalGate
) -> None:
    """Register the read-only ``describe_tool`` consent minter."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def describe_tool(
        tool: str, args: dict[str, Any] | None = None
    ) -> ConsentToken:
        """Mint a short-lived consent token for a **destructive** tool, bound to
        the exact ``(tool, args)``. Send it as ``consent=<token>`` on the call;
        changed args, expiry, and replay are refused with ``CONSENT_MISMATCH``.
        Other safety classes need no consent."""
        target = await mcp.get_tool(tool)
        if target is None:
            raise AgentToolError(
                "RESOURCE_NOT_FOUND",
                f"Unknown tool '{tool}'.",
                required="tool",
                next_call=NextCall(
                    tool="godot_list_toolsets", args={}, reason="discover the tool surface"
                ),
            )
        safety = (target.meta or {}).get("safety_class")
        call_args = dict(args or {})
        if safety != "destructive":
            return ConsentToken(
                tool=tool,
                consent_required=False,
                hint="Consent is required only for destructive tools.",
            )
        # Validate against the target's input schema (the same schema the client
        # sees). A malformed describe is a validation error, not a token.
        schema = getattr(target, "parameters", None) or {}
        try:
            Draft202012Validator(schema).validate(call_args)
        except JSONSchemaValidationError as exc:
            location = ".".join(str(part) for part in exc.path) or "args"
            raise AgentToolError(
                "VALIDATION_ERROR",
                f"Invalid args for '{tool}' at {location}: {exc.message}",
                required="args",
            ) from exc
        # With a webhook configured, approval happens *here*; the token then
        # carries the human's approval for these exact args.
        if approval.webhook_url:
            try:
                await approval.require(tool, safety, call_args)
            except PreconditionError as exc:
                raise exc.as_tool_error() from exc
        try:
            token, expires_at = consent.mint(tool, call_args)
        except ConsentError as exc:  # pragma: no cover - mint does not fail today
            raise AgentToolError("CONSENT_MISMATCH", exc.hint) from exc
        return ConsentToken(
            tool=tool,
            consent_required=True,
            token=token,
            expires_at=expires_at,
        )
