"""Contract tests for the health_check tool (issue #4).

Exercises the real FastMCP server over the in-memory client: the tool is listed,
carries its safety class, and reports the live bridge connection state.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server import __version__
from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server, list_tools_by_safety_class
from tests.fakes import FakeAddonConnection, connector_for, flaky_connector

pytestmark = pytest.mark.asyncio


def _server_with_bridge(bridge: Bridge) -> FastMCP:
    return create_server(ServerConfig(), bridge=bridge)


async def test_health_check_is_listed_as_read_only() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "health_check" in names
    health = next(t for t in tools if t.name == "health_check")
    assert health.meta is not None and health.meta.get("safety_class") == "read_only"


async def test_health_check_reports_connected_bridge() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        result = await client.call_tool("health_check", {})
    payload = result.structured_content
    assert payload["server"] == "godot-mcp"
    assert payload["version"] == __version__
    assert payload["bridge_connected"] is True
    assert payload["bridge_url"] == ServerConfig().bridge.url


async def test_health_check_reports_disconnected_when_godot_absent() -> None:
    # A connector that always fails ⇒ lifespan connect is suppressed ⇒ disconnected.
    bridge = Bridge(
        ServerConfig().bridge,
        connector=flaky_connector(fail_times=99, connection=FakeAddonConnection()),
    )
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        result = await client.call_tool("health_check", {})
    assert result.structured_content["bridge_connected"] is False


async def test_list_tools_by_safety_class_groups_health_check() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    grouped = await list_tools_by_safety_class(server)
    assert "health_check" in grouped["read_only"]
