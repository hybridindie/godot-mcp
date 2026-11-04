"""Server-global toolset gating middleware (issue #364).

Godot Editor MCP is a single-user, locally-run MCP server — one client per Godot
instance. Per-session isolation was dead code on the sessionless
``2026-07-28`` protocol real clients use (a fresh ``session_id`` per call), and
``Middleware.on_initialize`` violated ``.claude/rules/async-patterns.md``.

The enabled set is a single server-global set: ``enable_toolset`` /
``disable_toolset`` mutate it directly, and every client sees the same surface.
The default surface (core + inspection) is enforced from the first call with
no server-initiated hook.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_server.agent_errors import AgentToolError
from mcp_server.categories import CORE_TAG
from mcp_server.models.envelope import NextCall

logger = logging.getLogger(__name__)


class ToolsetMiddleware(Middleware):
    """Server-global toolset gating: filter ``on_list_tools`` and gate
    ``on_call_tool`` against a single process-wide enabled set.

    The set starts at the default (core + inspection). ``enable_toolset`` /
    ``disable_toolset`` mutate it via :meth:`enabled` / :meth:`set_enabled`.
    All clients — sessionless or legacy — share the same set; there is no
    per-session isolation, by design (single-user local server, issue #364).
    """

    def __init__(
        self,
        default_enabled: frozenset[str] | None = None,
    ) -> None:
        if default_enabled is None:
            from mcp_server.toolsets import DEFAULT_ENABLED

            default_enabled = DEFAULT_ENABLED
        self._enabled: set[str] = {CORE_TAG} | set(default_enabled)

    def enabled(self) -> set[str]:
        """Return a copy of the server-global enabled toolset set."""
        return set(self._enabled)

    def set_enabled(self, enabled: set[str]) -> None:
        """Replace the server-global enabled set (preserves ``core``)."""
        self._enabled = {CORE_TAG} | set(enabled)

    async def on_list_tools(self, context: MiddlewareContext, call_next: Any) -> Any:
        tools = await call_next(context)
        return [t for t in tools if self._is_visible(t, self._enabled)]

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        allowed, tool = await self._call_allowed(context)
        if not allowed:
            tags = set(getattr(tool, "tags", set()) or set()) - {CORE_TAG}
            category = next(iter(tags), None)
            raise AgentToolError(
                "PRECONDITION_FAILED",
                f"Tool '{context.message.name}' is not enabled. "
                f"Call godot_list_toolsets() to see available toolsets, then "
                f"godot_enable_toolset(category) to expose its tools.",
                required="toolset",
                next_call=(
                    NextCall(
                        tool="godot_enable_toolset",
                        args={"category": category},
                        reason=f"enable the '{category}' toolset",
                    )
                    if category
                    else None
                ),
            )
        return await call_next(context)

    def _is_visible(self, tool: Any, enabled: set[str]) -> bool:
        return _tag_visible(getattr(tool, "tags", set()) or set(), enabled)

    async def _call_allowed(self, context: MiddlewareContext) -> tuple[bool, Any | None]:
        name = context.message.name
        ctx = context.fastmcp_context
        if ctx is None:
            return True, None
        try:
            tool = await ctx.fastmcp.get_tool(name)
        except ToolError:
            return True, None
        except Exception:
            # Fail-open here (not fail-closed) so the agent can still reach
            # core recovery tools (godot_list_toolsets, godot_enable_toolset)
            # when an internal lookup error occurs. The approval middleware
            # is the security-critical gate and fails closed; the toolset gate
            # is a surface-management convenience. Logged at error so the
            # failure is visible, not silent.
            logger.error(
                "unexpected error looking up tool %r; allowing call (toolset "
                "gate fails open so core recovery tools stay reachable)",
                name,
                exc_info=True,
            )
            return True, None
        if tool is None:
            return True, None
        return self._is_visible(tool, self._enabled), tool


def _tag_visible(tags: set[str], enabled: set[str]) -> bool:
    """Whether a tool with ``tags`` is visible given the ``enabled`` set."""
    if CORE_TAG in tags:
        return True
    return bool(tags & enabled)