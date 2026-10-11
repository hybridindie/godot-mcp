"""The check_for_updates tool (issue #629).

A ``read_only`` tool: opt-in (``GODOT_MCP_CHECK_UPDATES``) and offline by default.
When enabled it queries the release feed for the latest published version and
reports whether the running server is behind — and tells the editor dock so the
human sees it too.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.safety import READ_ONLY
from mcp_server.updates import UpdateChecker, UpdateStatus


def register_updates(mcp: FastMCP, bridge: Bridge, checker: UpdateChecker) -> None:
    """Register check_for_updates on the given server."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def check_for_updates() -> UpdateStatus:
        """Check whether a newer godot-mcp release is available.

        Opt-in and offline by default: with ``GODOT_MCP_CHECK_UPDATES`` unset the
        result reports ``enabled: false`` and makes no network request. When enabled
        it queries the release feed and reports ``{current, latest, update_available,
        url}``; an unreachable feed returns an ``error``/``hint`` rather than failing.
        Read-only — never touches the Godot project.
        """
        status = await checker.check(force=True)
        if status.update_available and bridge.connected:
            # Surface it in the editor dock too — same fire-and-forget push the
            # server uses for the enabled-toolsets row (#592).
            await bridge.notify(
                "cmd_update_available",
                {
                    "current": status.current,
                    "latest": status.latest or "",
                    "url": status.url or "",
                },
            )
        return status


__all__ = ["register_updates"]
