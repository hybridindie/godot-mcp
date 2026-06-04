"""Bridge configuration (issue #3).

The bridge URL and request timeout are configuration, never hard-coded in
library code (see .claude/rules/architecture.md). Defaults are localhost-only
with no auth, per the v1 design.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_BRIDGE_URL = "ws://localhost:9080"
DEFAULT_REQUEST_TIMEOUT = 10.0

# MCP HTTP transport defaults (distinct from Godot's bridge port 9080).
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 9090

# Environment overrides.
BRIDGE_URL_ENV = "GODOT_MCP_BRIDGE_URL"

Transport = Literal["stdio", "http"]


def _parse_transport(value: str | None) -> Transport:
    """Validate and narrow a transport string to the supported literal."""
    if value == "stdio":
        return "stdio"
    if value == "http":
        return "http"
    return "stdio"


class BridgeConfig(BaseModel):
    """Connection settings for the Godot addon bridge."""

    url: str = DEFAULT_BRIDGE_URL
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Build config from the environment, falling back to localhost defaults."""
        return cls(url=os.environ.get(BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL))


class ServerConfig(BaseModel):
    """Top-level MCP server configuration.

    Transport defaults to ``stdio`` (the spec'd, auth-free local transport);
    ``http`` exposes the server over Streamable HTTP for clients that want a
    long-lived shared server. ``permission_mode`` is plumbed here but enforced in
    issue #14.
    """

    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    transport: Transport = "stdio"
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT
    log_level: str = "INFO"
    permission_mode: str = "ask"
    # Runtime loop (issue #13): path to the Godot binary and the project directory.
    # Both optional — the binary is auto-discovered and the project dir falls back to
    # the connected editor's project.
    godot_bin: str | None = None
    godot_project_dir: str | None = None

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Build full server config from the environment."""
        return cls(
            bridge=BridgeConfig.from_env(),
            transport=_parse_transport(os.environ.get("GODOT_MCP_TRANSPORT", "stdio")),
            host=os.environ.get("GODOT_MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
            port=int(os.environ.get("GODOT_MCP_HTTP_PORT", DEFAULT_HTTP_PORT)),
            log_level=os.environ.get("GODOT_MCP_LOG_LEVEL", "INFO"),
            permission_mode=os.environ.get("GODOT_MCP_PERMISSION_MODE", "ask"),
            godot_bin=os.environ.get("GODOT_MCP_GODOT_BIN"),
            godot_project_dir=os.environ.get("GODOT_MCP_PROJECT_DIR"),
        )
