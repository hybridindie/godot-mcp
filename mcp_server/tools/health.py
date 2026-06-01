"""The health_check tool (issue #4).

A ``read_only`` tool: it reports server identity/version and whether the Godot
bridge is currently connected. Thin delegation — the handler just assembles a
typed model from injected state (see .claude/rules/architecture.md).
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server import __version__
from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.health import HealthStatus
from mcp_server.safety import READ_ONLY


def build_health(bridge: Bridge, config: ServerConfig) -> HealthStatus:
    """Assemble the current health status from injected state (pure, testable)."""
    return HealthStatus(
        server="godot-mcp",
        version=__version__,
        transport=config.transport,
        bridge_url=config.bridge.url,
        bridge_connected=bridge.connected,
    )


def register_health(mcp: FastMCP, bridge: Bridge, config: ServerConfig) -> None:
    """Register health_check on the given server."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def health_check() -> HealthStatus:
        """Report server version and whether the Godot editor bridge is connected.

        Use this first to confirm the server is up and that Godot is reachable
        before issuing other commands. Never mutates anything.
        """
        return build_health(bridge, config)
