"""The health_check tool (issue #4).

A ``read_only`` tool: it reports server identity/version and whether the Godot
bridge is currently connected. Thin delegation — the handler just assembles a
typed model from injected state (see .opencode/rules/architecture.md).
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server import __version__
from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.health import HealthStatus
from mcp_server.safety import READ_ONLY
from mcp_server.versions import version_notice


def build_health(
    bridge: Bridge,
    config: ServerConfig,
    *,
    addon_version: str | None = None,
    notice: str | None = None,
) -> HealthStatus:
    """Assemble the current health status from injected state (pure, testable)."""
    return HealthStatus(
        server="godot-mcp",
        version=__version__,
        transport=config.transport,
        bridge_url=config.bridge.url,
        bridge_connected=bridge.connected,
        addon_version=addon_version,
        version_notice=notice,
        bridge_bind_error=bridge.bind_error,
    )


def register_health(mcp: FastMCP, bridge: Bridge, config: ServerConfig) -> None:
    """Register health_check on the given server."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def health_check() -> HealthStatus:
        """Report server version and whether the Godot editor bridge is connected.

        Use this first to confirm the server is up and that Godot is reachable
        before issuing other commands. Also reports the connected addon's version
        and flags a server↔addon version mismatch. Never mutates anything.
        """
        addon_version: str | None = None
        if bridge.connected:
            info = await bridge.addon_info() or {}
            addon_version = info.get("addon_version")
        return build_health(
            bridge,
            config,
            addon_version=addon_version,
            notice=version_notice(__version__, addon_version),
        )
