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
from mcp_server.server import create_server
from mcp_server.tools.health import build_health
from tests.fakes import FakeAddonConnection, connector_for, null_serve

pytestmark = pytest.mark.asyncio


def _server_with_bridge(bridge: Bridge) -> FastMCP:
    return create_server(ServerConfig(), bridge=bridge)


async def test_health_check_is_listed_as_read_only() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "godot_health_check" in names
    health = next(t for t in tools if t.name == "godot_health_check")
    assert health.meta is not None and health.meta.get("safety_class") == "read_only"


async def test_health_check_reports_connected_bridge() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        result = await client.call_tool("godot_health_check", {})
    payload = result.structured_content
    assert payload["server"] == "godot-mcp"
    assert payload["version"] == __version__
    assert payload["bridge_connected"] is True
    assert payload["bridge_url"] == ServerConfig().bridge.url


async def test_health_check_reports_disconnected_when_editor_absent() -> None:
    # The bridge is listening but no editor has connected to it yet ⇒ the server boots
    # fine and health reports disconnected (it never blocks on the editor being up).
    bridge = Bridge(ServerConfig().bridge, serve=null_serve)
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        result = await client.call_tool("godot_health_check", {})
    assert result.structured_content["bridge_connected"] is False


async def test_health_reports_the_attached_engine_support() -> None:
    # #588: health classifies the engine from the peer hello against the support
    # surface (floor 4.4, validated 4.7, verified 4.8-beta2). Pure build_health:
    # the hello is populated by the bridge, not by a tool round-trip.
    bridge = Bridge(ServerConfig().bridge)
    bridge._peer_identity = {"godot_version": "4.8.beta2.official.cafc17a1"}
    status = build_health(bridge, ServerConfig())
    assert status.godot_version == "4.8.beta2.official.cafc17a1"
    assert status.godot_support is not None
    assert status.godot_support.status == "prerelease"
    assert status.godot_support.validated == "4.7"
    assert status.godot_support.verified_against == "4.8-beta2"


async def test_health_check_without_editor_reports_disconnected_support() -> None:
    bridge = Bridge(ServerConfig().bridge, serve=null_serve)
    server = _server_with_bridge(bridge)
    async with Client(server) as client:
        result = await client.call_tool("godot_health_check", {})
    assert result.structured_content["godot_support"]["status"] == "disconnected"


async def test_list_tools_by_safety_class_groups_health_check() -> None:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    server = _server_with_bridge(bridge)
    grouped: dict[str, list[str]] = {}
    async with Client(server, mode="legacy") as client:
        tools = await client.list_tools()
    for tool in tools:
        safety_class = (tool.meta or {}).get("safety_class", "unclassified")
        grouped.setdefault(safety_class, []).append(tool.name)
    assert "godot_health_check" in grouped["read_only"]
