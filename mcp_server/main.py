"""stdio (and optional Streamable HTTP) entrypoint for the godot-mcp server.

Run with ``uv run godot-mcp`` (or ``python -m mcp_server.main``). Transport
defaults to stdio; set ``GODOT_MCP_TRANSPORT=http`` (with ``GODOT_MCP_HTTP_HOST`` /
``GODOT_MCP_HTTP_PORT``) for a long-lived HTTP server. The FastMCP runtime owns
the event loop — we never call ``asyncio.run`` here
(see .claude/rules/async-patterns.md).
"""

from __future__ import annotations

import logging

from mcp_server.config import ServerConfig
from mcp_server.logging_setup import configure_logging
from mcp_server.server import create_server

logger = logging.getLogger(__name__)


def main() -> None:
    """Build the server from the environment and run it on the configured transport."""
    config = ServerConfig.from_env()
    configure_logging(config.log_level)
    logger.info("starting godot-mcp", extra={"transport": config.transport})

    server = create_server(config)
    try:
        if config.transport == "http":
            server.run(transport="http", host=config.host, port=config.port)
        else:
            server.run(transport="stdio")
    except KeyboardInterrupt:
        # Ctrl-C is the ordinary way to stop a long-lived server; exit quietly rather
        # than dumping the runtime's shutdown traceback to the console.
        logger.info("godot-mcp interrupted; shutting down")


if __name__ == "__main__":
    main()
