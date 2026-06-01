"""Unit tests for ServerConfig (issue #4)."""

from __future__ import annotations

import pytest

from mcp_server.config import DEFAULT_BRIDGE_URL, ServerConfig


def test_defaults_are_stdio_localhost() -> None:
    config = ServerConfig()
    assert config.transport == "stdio"
    assert config.bridge.url == DEFAULT_BRIDGE_URL
    assert config.log_level == "INFO"
    # The MCP HTTP port is distinct from Godot's bridge port (9080).
    assert config.port != 9080


def test_from_env_reads_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GODOT_MCP_TRANSPORT", "http")
    monkeypatch.setenv("GODOT_MCP_HTTP_HOST", "0.0.0.0")
    monkeypatch.setenv("GODOT_MCP_HTTP_PORT", "9095")
    monkeypatch.setenv("GODOT_MCP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("GODOT_MCP_BRIDGE_URL", "ws://localhost:9081")

    config = ServerConfig.from_env()
    assert config.transport == "http"
    assert config.host == "0.0.0.0"
    assert config.port == 9095
    assert config.log_level == "DEBUG"
    assert config.bridge.url == "ws://localhost:9081"


def test_from_env_rejects_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GODOT_MCP_TRANSPORT", "carrier-pigeon")
    with pytest.raises(ValueError):
        ServerConfig.from_env()
