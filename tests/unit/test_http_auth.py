"""Contract tests for HTTP transport auth (issue #226)."""

from __future__ import annotations

import os

import pytest

from mcp_server.config import ServerConfig


def test_loopback_http_allowed_without_token() -> None:
    """Loopback HTTP (127.0.0.1) is allowed without a token — localhost-only is the default."""
    config = ServerConfig(transport="http", host="127.0.0.1")
    assert config.auth_token is None
    config.validate_http_auth()  # should not raise


def test_non_loopback_http_without_token_raises() -> None:
    """Non-loopback HTTP without a token is refused — unauthenticated RCE surface."""
    config = ServerConfig(transport="http", host="0.0.0.0")
    assert config.auth_token is None
    with pytest.raises(ValueError, match="GODOT_MCP_AUTH_TOKEN"):
        config.validate_http_auth()


def test_non_loopback_http_with_token_allowed() -> None:
    """Non-loopback HTTP with a token is allowed."""
    config = ServerConfig(transport="http", host="0.0.0.0", auth_token="secret-token")
    config.validate_http_auth()  # should not raise


def test_stdio_transport_never_requires_token() -> None:
    """stdio never needs auth — it's a local subprocess."""
    config = ServerConfig(transport="stdio", host="0.0.0.0")
    config.validate_http_auth()  # should not raise


def test_auth_token_from_env() -> None:
    """GODOT_MCP_AUTH_TOKEN sets the token."""

    os.environ["GODOT_MCP_AUTH_TOKEN"] = "env-token-123"
    try:
        config = ServerConfig.from_env()
    finally:
        del os.environ["GODOT_MCP_AUTH_TOKEN"]
    assert config.auth_token == "env-token-123"