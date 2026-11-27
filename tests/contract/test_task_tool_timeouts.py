"""Contract: task-enabled bridge tools get a bridge timeout longer than the
default request timeout (#315 follow-up).

``task=True`` frees the MCP request, but ``bake_navigation_mesh`` still sends
its bridge command with the 10s default, so a long bake times out anyway.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import (
    DEFAULT_LONG_REQUEST_TIMEOUT,
    LONG_REQUEST_TIMEOUT_ENV,
    ServerConfig,
    long_request_timeout,
)
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": True, "path": "res://m.tscn"})
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_node_persistence":
        return ResponseEnvelope.success(command.id, {"node_path": "Nav", "persisted": True})
    if command.command == "cmd_bake_navigation_mesh":
        return ResponseEnvelope.success(command.id, {"node_path": "Nav", "baked": True})
    return make_addon_responder(godot_version="4.7.2-stable")(command)


async def _bake_timeout(config: ServerConfig) -> float | None:
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection(_responder)))
    seen: dict[str, float | None] = {}
    real_send = bridge.send

    async def spy(
        command: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> ResponseEnvelope:
        seen[command] = timeout
        return await real_send(command, params, timeout=timeout)

    bridge.send = spy  # type: ignore[method-assign]
    server = create_server(config, bridge=bridge)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        await client.call_tool("godot_navigation_bake_mesh", {"node_path": "Nav"})
    return seen["cmd_bake_navigation_mesh"]


async def test_bake_navigation_mesh_uses_a_longer_bridge_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real environment must not decide this test (an exported override at or
    # below the default request timeout would fail it spuriously).
    monkeypatch.delenv(LONG_REQUEST_TIMEOUT_ENV, raising=False)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection(_responder)))
    seen: dict[str, float | None] = {}
    real_send = bridge.send

    async def spy(
        command: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> ResponseEnvelope:
        seen[command] = timeout
        return await real_send(command, params, timeout=timeout)

    bridge.send = spy  # type: ignore[method-assign]
    server = create_server(config, bridge=bridge)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        await client.call_tool("godot_navigation_bake_mesh", {"node_path": "Nav"})
    timeout = seen["cmd_bake_navigation_mesh"]
    assert timeout is not None and timeout > config.bridge.request_timeout


async def test_long_request_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LONG_REQUEST_TIMEOUT_ENV, raising=False)
    assert long_request_timeout() == DEFAULT_LONG_REQUEST_TIMEOUT == 120.0


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5"])
async def test_long_request_timeout_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(LONG_REQUEST_TIMEOUT_ENV, raw)
    assert long_request_timeout() == DEFAULT_LONG_REQUEST_TIMEOUT


async def test_long_request_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LONG_REQUEST_TIMEOUT_ENV, "300")
    assert long_request_timeout() == 300.0
    assert await _bake_timeout(ServerConfig()) == 300.0
