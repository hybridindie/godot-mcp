"""Contract tests for per-session toolset gating (issue #227)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _tool_names(client: Client) -> set[str]:
    """Get tool names the client can see."""
    import asyncio

    tools = asyncio.get_event_loop().run_until_complete(client.list_tools())
    return {t.name for t in tools}


async def test_isolation_one_client_enables_other_does_not_see() -> None:
    """Two concurrent clients have isolated toolset state — one enabling a toolset
    does not expose it to the other."""
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        tools_a_before = {t.name for t in await a.list_tools()}
        tools_b_before = {t.name for t in await b.list_tools()}

        # Both start with the same default surface (core + inspection).
        assert tools_a_before == tools_b_before

        # Client A enables scene_edit.
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools_a_after = {t.name for t in await a.list_tools()}
        tools_b_after = {t.name for t in await b.list_tools()}

        # A now sees scene_edit tools, B does not.
        assert "godot_scene_edit_create_node" in tools_a_after
        assert "godot_scene_edit_create_node" not in tools_b_after
        # B's surface didn't change.
        assert tools_b_before == tools_b_after


async def test_disable_isolates_per_session() -> None:
    """Disabling a toolset in one session does not affect another."""
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        # Both start with inspection enabled by default.
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await b.call_tool("godot_enable_toolset", {"category": "scene_edit"})

        # A disables scene_edit.
        await a.call_tool("godot_disable_toolset", {"category": "scene_edit"})
        tools_a = {t.name for t in await a.list_tools()}
        tools_b = {t.name for t in await b.list_tools()}

        assert "godot_scene_edit_create_node" not in tools_a
        assert "godot_scene_edit_create_node" in tools_b


async def test_list_toolsets_reflects_session_state() -> None:
    """list_toolsets reports per-session enabled state, not global."""
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result_a = await a.call_tool("godot_list_toolsets", {})
        result_b = await b.call_tool("godot_list_toolsets", {})
        a_scene = next(ts for ts in result_a.structured_content["result"] if ts["name"] == "scene_edit")
        b_scene = next(ts for ts in result_b.structured_content["result"] if ts["name"] == "scene_edit")
        assert a_scene["enabled"] is True
        assert b_scene["enabled"] is False


async def test_default_surface_unchanged() -> None:
    """The default surface (core + inspection) is unchanged for new clients."""
    server, _ = _build()
    async with Client(server) as client:
        result = await client.call_tool("godot_list_toolsets", {})
        statuses = {ts["name"]: ts["enabled"] for ts in result.structured_content["result"]}
        assert statuses["core"] is True
        assert statuses["inspection"] is True
        assert statuses["scene_edit"] is False


async def test_call_tool_blocked_when_not_enabled_in_session() -> None:
    """A tool call is blocked when the toolset is not enabled in the caller's session."""
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": "root", "node_type": "Node", "node_name": "test"},
            raise_on_error=False,
        )
        assert result.is_error
        assert "not enabled" in str(result.content).lower() or "toolset" in str(result.content).lower()