"""FastMCP server factory (issue #4).

Builds the AI-facing MCP server: wires the Godot bridge, registers tools, and
manages the bridge lifecycle via the server lifespan. The server is
transport-agnostic — ``main.py`` chooses stdio (default) or Streamable HTTP.

No I/O happens at import time; the bridge connects on startup (best-effort, so a
missing editor never blocks the server) and closes on shutdown
(see .claude/rules/async-patterns.md).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.tools.health import register_health

logger = logging.getLogger(__name__)

SERVER_NAME = "godot-mcp"


def create_server(config: ServerConfig | None = None, bridge: Bridge | None = None) -> FastMCP:
    """Create the FastMCP server, wiring the bridge and registering tools."""
    config = config or ServerConfig()
    bridge = bridge or Bridge(config.bridge)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        # Best-effort connect: if Godot isn't running, start anyway and report
        # disconnected via health_check rather than failing to boot.
        with contextlib.suppress(Exception):
            await bridge.connect()
            logger.info("bridge connected", extra={"url": config.bridge.url})
        try:
            yield
        finally:
            await bridge.close()

    mcp = FastMCP(SERVER_NAME, lifespan=lifespan)
    register_health(mcp, bridge, config)
    return mcp


async def list_tools_by_safety_class(mcp: FastMCP) -> dict[str, list[str]]:
    """Group registered tool names by their ``safety_class`` for agent introspection.

    Tools without a declared safety class are grouped under ``"unclassified"``.
    """
    grouped: dict[str, list[str]] = {}
    for tool in await mcp.list_tools():
        safety_class = (tool.meta or {}).get("safety_class", "unclassified")
        grouped.setdefault(safety_class, []).append(tool.name)
    return grouped
