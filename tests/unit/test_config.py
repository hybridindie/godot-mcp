"""Unit tests for bridge configuration (issue #3)."""

from __future__ import annotations

import pytest

from mcp_server.config import BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL, BridgeConfig


def test_default_url_is_localhost_9080() -> None:
    assert BridgeConfig().url == "ws://localhost:9080"
    assert DEFAULT_BRIDGE_URL == "ws://localhost:9080"


def test_from_env_defaults_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BRIDGE_URL_ENV, raising=False)
    assert BridgeConfig.from_env().url == DEFAULT_BRIDGE_URL


def test_from_env_honors_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BRIDGE_URL_ENV, "ws://localhost:9999")
    assert BridgeConfig.from_env().url == "ws://localhost:9999"
