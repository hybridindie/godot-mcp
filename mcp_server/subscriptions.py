"""Server-side ``subscriptions/listen`` support (issue #620).

On the sessionless MCP ``2026-07-28`` protocol there is no standing
server→client channel: the spec forbids unsolicited change notifications, so a
``notifications/tools/list_changed`` reaches a client only on a
``subscriptions/listen`` stream that client explicitly opens. FastMCP drives the
low-level mcp ``Server`` directly and never registered that method, so on the
modern era it advertised ``tools.listChanged: false`` and capable clients
(Claude Code CLI) never subscribed — the gap tracked upstream as
`PrefectHQ/fastmcp#4920 <https://github.com/PrefectHQ/fastmcp/issues/4920>`_.

This module fills it. It installs a ``ListenHandler`` backed by an
``InMemorySubscriptionBus`` on FastMCP's low-level server — the same
construction mcp's own ``MCPServer`` uses — and exposes
:meth:`ToolsetSubscriptionHub.publish_tools_changed` so toolset toggles reach
subscribers. Registering the method also flips the advertised
``tools.listChanged`` to ``true`` on ``2026-07-28``: the mcp SDK derives that
flag from whether ``subscriptions/listen`` is served, not from FastMCP's legacy
``NotificationOptions``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler
from mcp.shared.subscriptions import ToolsListChanged
from mcp_types import SubscriptionsListenRequestParams

logger = logging.getLogger(__name__)

# The request method the SDK keys the modern `tools.listChanged` capability on.
_LISTEN_METHOD = "subscriptions/listen"


class ToolsetSubscriptionHub:
    """Owns the subscription bus and publishes toolset-change events.

    The bus is server-global, matching the server-global enabled-toolset set
    (issue #364): every subscriber sees every toggle.
    """

    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus if bus is not None else InMemorySubscriptionBus()

    async def publish_tools_changed(self) -> None:
        """Fan ``notifications/tools/list_changed`` out to every open listen stream.

        Fire-and-forget by design: the toggle already applied, so a publish
        failure must not fail the tool call — but it is logged, never swallowed
        silently.
        """
        try:
            await self._bus.publish(ToolsListChanged())
        except Exception:
            logger.warning(
                "publishing tools/list_changed to subscriptions failed; "
                "toolset toggle already applied",
                exc_info=True,
            )


def install_toolset_subscriptions(
    mcp: FastMCP, hub: ToolsetSubscriptionHub | None = None
) -> ToolsetSubscriptionHub:
    """Register ``subscriptions/listen`` on FastMCP's low-level server.

    FastMCP exposes no public hook for a spec request method (its SEP-2133
    extension API deliberately rejects spec methods), so we register on the
    low-level server directly — the exact wiring mcp's own ``MCPServer`` does
    (``on_subscriptions_listen=ListenHandler(bus)``). Idempotent: re-installing
    on a server that already serves the method is a no-op.

    Returns the hub whose :meth:`~ToolsetSubscriptionHub.publish_tools_changed`
    should be called on every toolset toggle.
    """
    hub = hub or ToolsetSubscriptionHub()
    server = mcp._mcp_server
    handlers = getattr(server, "_request_handlers", {})
    if _LISTEN_METHOD not in handlers:
        server.add_request_handler(
            _LISTEN_METHOD,
            SubscriptionsListenRequestParams,
            ListenHandler(hub._bus),
        )
    return hub


__all__ = ["ToolsetSubscriptionHub", "install_toolset_subscriptions"]
