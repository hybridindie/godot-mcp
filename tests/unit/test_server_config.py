"""Unit tests for ServerConfig (issue #4)."""

from __future__ import annotations

import inspect

import pytest

from mcp_server.config import (
    DEFAULT_BRIDGE_URL,
    DEFAULT_MAX_INBOUND_MESSAGE_BYTES,
    BridgeConfig,
    ServerConfig,
)


def test_defaults_are_stdio_localhost() -> None:
    config = ServerConfig()
    assert config.transport == "stdio"
    assert config.bridge.url == DEFAULT_BRIDGE_URL
    assert config.log_level == "INFO"
    # The MCP HTTP port is distinct from Godot's bridge port (9080).
    assert config.port != 9080


def test_bridge_message_limit_admits_full_screenshot_frames() -> None:
    """#563: the websockets library's default inbound ``max_size`` is 1 MiB —
    a full 3D gameplay screenshot (base64 PNG) exceeds it, so the listener
    would drop the frame the addon just started sending. The default must be
    a deliberate, documented value large enough for normal captures."""
    config = BridgeConfig()
    assert config.max_inbound_message_bytes == DEFAULT_MAX_INBOUND_MESSAGE_BYTES
    assert config.max_inbound_message_bytes >= 16 * 1024 * 1024
    # The real listener must actually apply it (no dead config field).
    src = inspect.getsource(__import__("mcp_server.bridge", fromlist=["_default_serve"]))
    default_serve = src.split("async def _default_serve", 1)[1].split("\nasync def ", 1)[0]
    assert "max_size" in default_serve, "_default_serve must pass max_size to websockets.serve"


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


def test_from_env_falls_back_to_stdio_on_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GODOT_MCP_TRANSPORT", "carrier-pigeon")
    config = ServerConfig.from_env()
    # Unknown transports fall back to "stdio" rather than crashing.
    assert config.transport == "stdio"


def test_no_dead_permission_mode_field() -> None:
    # permission_mode was plumbed but never enforced; removed (issue #225).
    # Approval is webhook-only via ApprovalGate. The field must not reappear as a
    # misleading "permission gate" that does nothing.
    assert "permission_mode" not in ServerConfig.model_fields


def test_from_env_ignores_permission_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GODOT_MCP_PERMISSION_MODE", "deny")
    config = ServerConfig.from_env()
    assert not hasattr(config, "permission_mode")
