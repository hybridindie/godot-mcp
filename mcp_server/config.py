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
    long-lived shared server.

    There is no per-mode "permission" gate: safety is enforced by per-tool
    ``safety_class`` + ``dry_run``/``confirm`` (issue #14), plus the optional
    human-in-the-loop :class:`~mcp_server.safety.ApprovalGate` webhook below.
    """

    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    transport: Transport = "stdio"
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT
    log_level: str = "INFO"
    # Runtime loop (issue #13): path to the Godot binary and the project directory.
    # Both optional — the binary is auto-discovered and the project dir falls back to
    # the connected editor's project.
    godot_bin: str | None = None
    godot_project_dir: str | None = None
    # Human-in-the-loop approval (issue #14/#153). Opt-in: with no webhook,
    # destructive tools run as before (so evals/headless are never blocked).
    # ``fail_open`` decides whether an unreachable webhook approves or denies.
    approval_webhook: str | None = None
    approval_timeout: float = 30.0
    approval_fail_open: bool = True
    # HTTP transport auth (issue #226). Opt-in: loopback HTTP is allowed without a
    # token; a non-loopback bind requires a token or the server refuses to start.
    auth_token: str | None = None

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Build full server config from the environment."""
        return cls(
            bridge=BridgeConfig.from_env(),
            transport=_parse_transport(os.environ.get("GODOT_MCP_TRANSPORT", "stdio")),
            host=os.environ.get("GODOT_MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
            port=int(os.environ.get("GODOT_MCP_HTTP_PORT", DEFAULT_HTTP_PORT)),
            log_level=os.environ.get("GODOT_MCP_LOG_LEVEL", "INFO"),
            godot_bin=os.environ.get("GODOT_MCP_GODOT_BIN"),
            godot_project_dir=os.environ.get("GODOT_MCP_PROJECT_DIR"),
            approval_webhook=os.environ.get("GODOT_MCP_APPROVAL_WEBHOOK"),
            approval_timeout=float(os.environ.get("GODOT_MCP_APPROVAL_TIMEOUT", 30.0)),
            approval_fail_open=os.environ.get("GODOT_MCP_APPROVAL_FAIL_OPEN", "true").lower()
            != "false",
            auth_token=os.environ.get("GODOT_MCP_AUTH_TOKEN"),
        )

    def validate_http_auth(self) -> None:
        """Refuse a non-loopback HTTP bind unless an auth token is configured.

        Loopback (127.0.0.1 / localhost) is the default and safe without auth.
        Binding off-loopback exposes unauthenticated code execution (write_script,
        run_and_capture, export) — require a token or fail fast with a clear error.
        stdio is never gated (local subprocess).
        """
        if self.transport != "http":
            return
        if self.auth_token:
            return
        host = self.host
        if host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
            raise ValueError(
                f"HTTP transport bound to {host} (non-loopback) without GODOT_MCP_AUTH_TOKEN. "
                "Binding off-loopback exposes unauthenticated code execution. "
                "Set GODOT_MCP_AUTH_TOKEN to a bearer token, or bind 127.0.0.1."
            )
