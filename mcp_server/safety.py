"""Tool safety: classes, preconditions, confirmation, and dry-run (issue #14).

All safety/permission logic lives here, never in the addon
(see .claude/rules/mcp-tools.md). Tools are tagged with a ``safety_class`` via the
``READ_ONLY`` / ``MUTATING`` / ``DESTRUCTIVE`` / ``RUNTIME`` meta constants.

Preconditions raise a typed :class:`PreconditionError`; the
:func:`enforce_preconditions` decorator (applied by mutating/destructive tools in
issue #6) converts it to a ``ToolError`` so the agent gets a structured,
actionable message instead of a stack trace.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from typing import TYPE_CHECKING, Any

import httpx2 as httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.models.approval import ApprovalRequest, ApprovalResponse
from mcp_server.models.envelope import ErrorCode, ResponseEnvelope

if TYPE_CHECKING:
    from mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


class SafetyClass(StrEnum):
    """How risky a tool is. Drives the extra requirements below."""

    READ_ONLY = "read_only"  # never mutates
    MUTATING = "mutating"  # reversible editor change (UndoRedo); takes dry_run
    DESTRUCTIVE = "destructive"  # may be irreversible; takes dry_run + confirm
    RUNTIME = "runtime"  # controls game execution


def _meta(safety_class: SafetyClass) -> dict[str, str]:
    return {"safety_class": safety_class.value}


# Meta constants to tag tools with, e.g. ``@mcp.tool(meta=READ_ONLY)``.
READ_ONLY = _meta(SafetyClass.READ_ONLY)
MUTATING = _meta(SafetyClass.MUTATING)
DESTRUCTIVE = _meta(SafetyClass.DESTRUCTIVE)
RUNTIME = _meta(SafetyClass.RUNTIME)


# --- standard MCP annotations (issue #220) ---------------------------------
#
# Clients (e.g. Claude) consume the *standard* MCP ``annotations`` natively to
# reason about which tools are safe vs. state-changing; the custom ``safety_class``
# meta above only helps this server. Derive the standard hints from it so both are
# kept in sync from a single source of truth.


def annotations_for_safety_class(safety_class: str) -> ToolAnnotations | None:
    """Map a ``safety_class`` value to standard MCP :class:`ToolAnnotations`.

    Returns ``None`` for unknown / unclassified tools (no hints asserted).
    A fresh instance is returned per call so callers never share mutable state.
    """
    try:
        cls = SafetyClass(safety_class)
    except ValueError:
        return None
    if cls is SafetyClass.READ_ONLY:
        # Reads never mutate and are repeatable with no additional effect.
        return ToolAnnotations(read_only_hint=True, idempotent_hint=True)
    if cls is SafetyClass.DESTRUCTIVE:
        return ToolAnnotations(read_only_hint=False, destructive_hint=True)
    # mutating (reversible via UndoRedo) and runtime (controls execution):
    # state-changing but not destructive.
    return ToolAnnotations(read_only_hint=False, destructive_hint=False)


async def _iter_registered_tools(mcp: FastMCP) -> AsyncIterator[Any]:
    """Yield every registered tool object, including toolset-gated (disabled) ones.

    FastMCP's server-level ``list_tools()`` filters out disabled tools, but
    annotations must be applied to *all* tools so they are already correct the
    moment a gated toolset is enabled. FastMCP 4.0 exposes the local provider
    as the public ``mcp.local_provider`` attribute, and its ``list_tools()``
    returns the unfiltered set (filtering happens at the server level, not the
    provider level — see ``LocalProvider.list_tools``).
    """
    for tool in await mcp.local_provider.list_tools():
        yield tool


async def _apply_safety_annotations_async(mcp: FastMCP) -> None:
    """Async implementation; ``apply_safety_annotations`` runs this on a loop."""
    async for tool in _iter_registered_tools(mcp):
        if tool.annotations is not None:
            continue
        safety_class = (tool.meta or {}).get("safety_class")
        if not safety_class:
            continue
        annotations = annotations_for_safety_class(safety_class)
        if annotations is not None:
            tool.annotations = annotations


async def apply_safety_annotations(mcp: FastMCP) -> None:
    """Set standard MCP ``annotations`` on every tool from its ``safety_class``.

    Call once after all tools are registered. An annotation set explicitly at
    registration is preserved (treated as an intentional override).

    Enumerates tools via the public async ``mcp.local_provider.list_tools()``
    (FastMCP 4.0). Must be called from an async context (e.g. inside the server
    lifespan or an async test).
    """
    await _apply_safety_annotations_async(mcp)


class PreconditionError(Exception):
    """A precondition for a tool was not met. Carries the structured fields the
    agent needs to recover (see the precondition envelope in docs/architecture.md).
    """

    def __init__(
        self,
        hint: str,
        required: str,
        error: ErrorCode | str = ErrorCode.PRECONDITION_FAILED,
    ) -> None:
        self.error = str(error)
        self.hint = hint
        self.required = required
        super().__init__(f"{self.error}: {hint}")

    def as_tool_error(self) -> ToolError:
        return ToolError(f"{self.error}: {self.hint} [required={self.required}]")


# --- preconditions ---------------------------------------------------------


def require_bridge_connected(bridge: Bridge) -> None:
    """Fail fast if the Godot editor bridge is not connected."""
    if not bridge.connected:
        raise PreconditionError(
            "Godot is not connected. Open the editor with the godot_mcp addon enabled.",
            required="bridge_connected",
            error=ErrorCode.BRIDGE_DISCONNECTED,
        )


async def require_active_scene(bridge: Bridge) -> None:
    """Fail fast if no scene is open in the editor."""
    require_bridge_connected(bridge)
    response = await bridge.send("cmd_get_active_scene")
    _raise_if_failed(response)
    if not (response.result or {}).get("is_open"):
        raise PreconditionError(
            "No scene is open. Recover, don't fail: call list_scenes() to see the "
            "project's scenes — then open_scene(path) to edit an existing one, or "
            "create_scene(root_type, scene_path) to start a new one (create_scene works "
            "with no scene open). Re-run this action once a scene is open.",
            required="active_scene",
        )


async def require_node_exists(bridge: Bridge, node_path: str) -> None:
    """Fail fast if ``node_path`` does not resolve in the active scene."""
    require_bridge_connected(bridge)
    response = await bridge.send("cmd_get_node_properties", {"node_path": node_path})
    if response.ok:
        return
    # Only a genuine not-found means "fix the path"; other failures (TIMEOUT,
    # BRIDGE_DISCONNECTED, no scene, …) propagate with their own error/required.
    if response.error == ErrorCode.RESOURCE_NOT_FOUND:
        raise PreconditionError(
            response.hint or f"No node at '{node_path}'.",
            required="node_exists",
            error=ErrorCode.RESOURCE_NOT_FOUND,
        )
    _raise_if_failed(response)


def require_godot_binary(binary: str | None) -> None:
    """Fail fast if no Godot binary is available for headless runner tools."""
    if binary is None:
        raise PreconditionError(
            "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
            required="godot_bin",
        )


def require_confirmation(confirm: bool, action: str) -> None:
    """Block a destructive action unless ``confirm=True`` was passed."""
    if not confirm:
        raise PreconditionError(
            f"'{action}' is destructive and may be irreversible. Pass confirm=true to proceed.",
            required="confirm",
        )


# --- human-in-the-loop approval (issue #153) -------------------------------

# A poster takes (url, request, timeout) and returns the webhook's verdict.
# Injected so the gate is unit-testable without a network.
ApprovalPoster = Callable[[str, ApprovalRequest, float], Awaitable[ApprovalResponse]]


def parse_approval_response(payload: Any) -> ApprovalResponse:
    """Parse a webhook body into a verdict. A reply we cannot parse fails *safe*
    (denied) rather than raising — a malformed response must never auto-approve a
    destructive action, even with ``fail_open=True``.
    """
    try:
        return ApprovalResponse.model_validate(payload)
    except ValidationError:
        return ApprovalResponse(approved=False, reason="malformed approval response")


async def post_approval(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
    """Default poster: POST the request as JSON and parse the verdict.

    Only transport-level failures (timeout, connection) propagate — those are the
    "webhook unreachable" case the gate's fail-open/closed policy handles. A reply
    with an unparseable body is a *received* verdict that fails safe to denied.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=request.model_dump(), timeout=timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError:
            return ApprovalResponse(approved=False, reason="non-JSON approval response")
        return parse_approval_response(payload)


@dataclass
class ApprovalGate:
    """Optional human approval for destructive (and, if wired, mutating/runtime)
    tools (issue #153).

    Opt-in: with ``webhook_url`` unset the gate auto-approves, so evals and
    headless runs are never blocked. When set, :meth:`require` POSTs an
    :class:`ApprovalRequest` and raises ``PreconditionError(APPROVAL_DENIED)`` on
    a denial. An unreachable/slow webhook approves when ``fail_open`` (default)
    or denies when not. Every decision is logged.
    """

    webhook_url: str | None = None
    timeout: float = 30.0
    fail_open: bool = True
    poster: ApprovalPoster = field(default=post_approval)
    clock: Callable[[], float] = field(default=time.time)

    @classmethod
    def from_config(cls, config: ServerConfig) -> ApprovalGate:
        return cls(
            webhook_url=config.approval_webhook,
            timeout=config.approval_timeout,
            fail_open=config.approval_fail_open,
        )

    async def require(
        self,
        action: str,
        safety_class: str,
        params: dict[str, Any],
        task_context: str | None = None,
    ) -> None:
        """Block ``action`` unless the webhook approves it. No-op without a webhook."""
        if not self.webhook_url:
            return  # opt-in: no webhook configured → auto-approve

        request = ApprovalRequest(
            action=action,
            safety_class=safety_class,
            params=params,
            task_context=task_context,
            timestamp=self.clock(),
        )
        try:
            response = await self.poster(self.webhook_url, request, self.timeout)
        except asyncio.CancelledError:
            raise  # never treat cancellation as a webhook failure
        except Exception:
            logger.warning(
                "approval webhook unreachable; failing %s",
                "open" if self.fail_open else "closed",
                extra={"action": action, "safety_class": safety_class},
                exc_info=True,
            )
            if self.fail_open:
                return
            raise PreconditionError(
                f"Approval webhook is unreachable; failing closed for '{action}'.",
                required="human_approval",
                error=ErrorCode.APPROVAL_DENIED,
            ) from None

        if response.approved:
            logger.info("approval granted", extra={"action": action})
            return
        logger.info("approval denied", extra={"action": action, "reason": response.reason})
        raise PreconditionError(
            response.reason or f"'{action}' was denied by the human approver.",
            required="human_approval",
            error=ErrorCode.APPROVAL_DENIED,
        )


def _raise_if_failed(response: ResponseEnvelope) -> None:
    if not response.ok:
        raise PreconditionError(
            response.hint or "A precondition check failed.",
            required=response.required or "unknown",
            error=response.error or ErrorCode.INTERNAL_ERROR,
        )


# --- enforcement decorator -------------------------------------------------

ToolFn = Callable[..., Awaitable[Any]]


def enforce_preconditions(fn: ToolFn) -> ToolFn:
    """Convert any :class:`PreconditionError` raised by a tool into a structured
    ``ToolError``. Applied to mutating/destructive tools (issue #6).
    """

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except PreconditionError as exc:
            raise exc.as_tool_error() from exc

    return wrapper


# --- introspection ---------------------------------------------------------


async def grouped_by_safety_class(mcp: FastMCP) -> dict[str, list[str]]:
    """Group registered tool names by ``safety_class`` (``"unclassified"`` if unset)."""
    grouped: dict[str, list[str]] = {}
    for tool in await mcp.list_tools():
        safety_class = (tool.meta or {}).get("safety_class", "unclassified")
        grouped.setdefault(safety_class, []).append(tool.name)
    return grouped


def register_safety_tools(mcp: FastMCP) -> None:
    """Register the agent-facing safety introspection tool."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def list_tools_by_safety_class() -> dict[str, list[str]]:
        """List every available tool grouped by its safety class
        (read_only / mutating / destructive / runtime). Call this to learn which
        tools are safe to call freely and which need ``dry_run``/``confirm``.
        """
        return await grouped_by_safety_class(mcp)
