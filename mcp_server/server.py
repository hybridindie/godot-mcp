"""FastMCP server factory (issue #4).

Builds the AI-facing MCP server: wires the Godot bridge, registers tools, and
manages the bridge lifecycle via the server lifespan. The server is
transport-agnostic — ``main.py`` chooses stdio (default) or Streamable HTTP.

No I/O happens at import time; the bridge connects on startup (best-effort, so a
missing editor never blocks the server) and closes on shutdown
(see .claude/rules/async-patterns.md).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.resources.context import register_resources
from mcp_server.runtime import GodotRunner, Runner
from mcp_server.safety import register_safety_tools
from mcp_server.tools.health import register_health
from mcp_server.tools.inspection import register_inspection
from mcp_server.tools.mutation import register_mutation
from mcp_server.tools.node_ops import register_node_ops
from mcp_server.tools.runtime import register_runtime
from mcp_server.tools.scripts import register_scripts
from mcp_server.toolsets import ToolsetManager, register_toolset_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "godot-mcp"


def create_server(
    config: ServerConfig | None = None,
    bridge: Bridge | None = None,
    runner: Runner | None = None,
) -> FastMCP:
    """Create the FastMCP server, wiring the bridge and registering tools."""
    config = config or ServerConfig()
    bridge = bridge or Bridge(config.bridge)
    runner = runner or GodotRunner(config)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        # Best-effort connect: if Godot isn't running, start anyway and report
        # disconnected via health_check rather than failing to boot — but log the
        # failure so a wrong URL / missing addon is diagnosable.
        try:
            await bridge.connect()
            logger.info("bridge connected", extra={"url": config.bridge.url})
        except Exception:
            logger.warning(
                "bridge not connected at startup; continuing (check the editor/addon)",
                extra={"url": config.bridge.url},
                exc_info=True,
            )
        try:
            yield
        finally:
            await bridge.close()

    mcp = FastMCP(SERVER_NAME, lifespan=lifespan)
    register_health(mcp, bridge, config)
    register_inspection(mcp, bridge)
    register_mutation(mcp, bridge)
    register_node_ops(mcp, bridge)
    register_resources(mcp, bridge)
    register_runtime(mcp, bridge, config, runner)
    register_scripts(mcp, bridge, config, runner)
    register_safety_tools(mcp)

    # Gate the tool surface by category, then apply the default exposure (core +
    # inspection on; scene_edit and future categories off until enabled).
    manager = ToolsetManager(mcp)
    register_toolset_tools(mcp, manager)
    manager.apply_defaults()
    return mcp
