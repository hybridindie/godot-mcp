"""Per-session toolset gating middleware (issue #227).

Replaces the process-global ``mcp.enable/disable(tags=)`` with per-session
isolation: each client session has its own set of enabled toolsets, so one
client enabling ``scene_edit`` does not expose it to another. Uses
``context.fastmcp_context.session_id`` to key the per-session state.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_server.categories import CORE_TAG

logger = logging.getLogger(__name__)


class ToolsetMiddleware(Middleware):
    """Per-session toolset gating: filter ``on_list_tools`` and gate ``on_call_tool``.

    Each session starts with the default enabled set (core + inspection). The
    ``enable_toolset``/``disable_toolset`` tools write into the session's set
    via :meth:`session_enabled`; this middleware reads it to filter list/call.
    """

    def __init__(
        self,
        default_enabled: frozenset[str] | None = None,
    ) -> None:
        if default_enabled is None:
            from mcp_server.toolsets import DEFAULT_ENABLED

            default_enabled = DEFAULT_ENABLED
        self._default_enabled: set[str] = {CORE_TAG} | set(default_enabled)
        self._sessions: dict[str, set[str]] = {}
        self._initialized: set[str] = set()

    async def on_initialize(self, context: MiddlewareContext, call_next: Any) -> Any:
        ctx = context.fastmcp_context
        if ctx is not None:
            sid = getattr(ctx, "session_id", None)
            if sid is not None:
                self._initialized.add(sid)
                self._sessions.setdefault(sid, set(self._default_enabled))
        return await call_next(context)

    def session_enabled(self, ctx: Any) -> set[str] | None:
        """Return the enabled toolset set for the session behind ``ctx``.

        Returns ``None`` when the session was not established via ``on_initialize``
        (sessionless protocol) — the middleware should not filter, since the
        client can't maintain per-session state across requests.
        """
        sid = getattr(ctx, "session_id", None)
        if sid is None or sid not in self._initialized:
            return None
        return set(self._sessions.setdefault(sid, set(self._default_enabled)))

    def set_session_enabled(self, ctx: Any, enabled: set[str]) -> None:
        """Write the enabled set for the session behind ``ctx``."""
        sid = getattr(ctx, "session_id", None)
        if sid is not None:
            self._sessions[sid] = enabled

    async def on_list_tools(self, context: MiddlewareContext, call_next: Any) -> Any:
        tools = await call_next(context)
        ctx = context.fastmcp_context
        if ctx is None:
            return tools
        enabled = self.session_enabled(ctx)
        if enabled is None:
            return tools
        return [t for t in tools if self._is_visible(t, enabled)]

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        ctx = context.fastmcp_context
        if ctx is None:
            return await call_next(context)
        enabled = self.session_enabled(ctx)
        if enabled is None:
            return await call_next(context)
        if not await self._is_call_allowed(context.message.name, ctx, enabled):
            raise ToolError(
                f"Tool '{context.message.name}' is not enabled in this session. "
                f"Call godot_list_toolsets() to see available toolsets, then "
                f"godot_enable_toolset(category) to expose its tools."
            )
        return await call_next(context)

    def _is_visible(self, tool: Any, enabled: set[str]) -> bool:
        tags: set[str] = getattr(tool, "tags", set()) or set()
        if CORE_TAG in tags:
            return True
        return bool(tags & enabled)

    async def _is_call_allowed(self, name: str, ctx: Any, enabled: set[str]) -> bool:
        if ctx is None:
            return True
        try:
            tool = await ctx.fastmcp.get_tool(name)
        except Exception:
            return True
        tags: set[str] = getattr(tool, "tags", set()) or set()
        if CORE_TAG in tags:
            return True
        return bool(tags & enabled)