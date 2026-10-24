"""Fail fast when the editor is not ready (issue #762).

The addon sends a 1s heartbeat (`cmd_editor_status`) reporting
``ready | importing | modal``; the bridge adds ``busy`` (a command is in flight)
and ``stale`` (no message within the deadline). A mutating/destructive tool is
refused with ``EDITOR_BUSY`` instead of waiting out the request timeout. A stale
editor is ``BRIDGE_DISCONNECTED`` — it is not going to answer.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware

from mcp_server.agent_errors import AgentToolError
from mcp_server.bridge import Bridge
from mcp_server.models.envelope import NextCall


class ReadinessMiddleware(Middleware):
    """Gate mutating/destructive calls on the editor's heartbeat state."""

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        tool = await self._get_tool(context)
        if tool is None or (getattr(tool, "meta", None) or {}).get("safety_class") not in (
            "mutating",
            "destructive",
        ):
            return await call_next(context)
        args = getattr(context.message, "arguments", None) or {}
        if args.get("dry_run"):
            return await call_next(context)
        status = self._bridge.editor_status
        if status == "stale":
            raise AgentToolError(
                "BRIDGE_DISCONNECTED",
                "The editor stopped responding (no heartbeat within 5s) — re-open Godot "
                "and check the addon's status dock.",
                required="bridge_connected",
                next_call=NextCall(
                    tool="godot_health_check",
                    args={},
                    reason="check whether the editor is reachable",
                ),
            )
        if status in ("importing", "modal", "busy"):
            raise AgentToolError(
                "EDITOR_BUSY",
                f"The editor is {status}; this mutating call was not sent. "
                "Wait for it to finish and retry.",
                required="editor_ready",
                next_call=NextCall(
                    tool="godot_health_check",
                    args={},
                    reason=f"check the editor status (currently {status})",
                ),
            )
        return await call_next(context)

    @staticmethod
    async def _get_tool(context: Any) -> Any:
        try:
            return await context.fastmcp_context.fastmcp.get_tool(context.message.name)
        except Exception:
            return None
