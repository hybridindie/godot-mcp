"""Contract tests: toolset gating is server-global shared state (issue #364).

godot-mcp is a single-user, locally-run MCP server. Per-session isolation was
removed in #364 — the enabled set is one process-wide set shared by all
clients. These tests pin the shared-state contract: an enable/disable by one
client is visible to every other client, and the default surface is enforced
without a server-initiated hook.
"""

from __future__ import annotations

import asyncio

import mcp_types
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.messages import MessageHandler

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_enable_in_one_client_is_visible_to_another() -> None:
    """Enabling a toolset in one client exposes it to a concurrent client —
    the enabled set is shared, not isolated per session.
    """
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        before_a = {t.name for t in await a.list_tools()}
        before_b = {t.name for t in await b.list_tools()}
        assert before_a == before_b  # both start with the default surface

        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        after_a = {t.name for t in await a.list_tools()}
        after_b = {t.name for t in await b.list_tools()}

        # A enabled it; both A and B now see scene_edit tools (shared state).
        assert "godot_scene_edit_create_node" in after_a
        assert "godot_scene_edit_create_node" in after_b


async def test_disable_in_one_client_affects_another() -> None:
    """Disabling a toolset in one session affects the other — shared state."""
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await b.call_tool("godot_enable_toolset", {"category": "scene_edit"})

        await a.call_tool("godot_disable_toolset", {"category": "scene_edit"})
        tools_a = {t.name for t in await a.list_tools()}
        tools_b = {t.name for t in await b.list_tools()}

        # A disabled it; both lose it (shared state, no isolation).
        assert "godot_scene_edit_create_node" not in tools_a
        assert "godot_scene_edit_create_node" not in tools_b


async def test_list_toolsets_reflects_shared_state() -> None:
    """list_toolsets reports the shared global state — both clients see the
    same enabled/disabled status for every toolset.
    """
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result_a = await a.call_tool("godot_list_toolsets", {})
        result_b = await b.call_tool("godot_list_toolsets", {})
        a_scene = next(
            ts for ts in result_a.structured_content["result"] if ts["name"] == "scene_edit"
        )
        b_scene = next(
            ts for ts in result_b.structured_content["result"] if ts["name"] == "scene_edit"
        )
        # Both report the shared state: scene_edit is enabled for both.
        assert a_scene["enabled"] is True
        assert b_scene["enabled"] is True


async def test_default_surface_unchanged() -> None:
    """The default surface (core + inspection) is unchanged for new clients."""
    server, _ = _build()
    async with Client(server) as client:
        result = await client.call_tool("godot_list_toolsets", {})
        statuses = {ts["name"]: ts["enabled"] for ts in result.structured_content["result"]}
        assert statuses["core"] is True
        assert statuses["inspection"] is True
        assert statuses["scene_edit"] is False


async def test_call_tool_blocked_when_not_enabled() -> None:
    """A tool call is blocked when the toolset is not enabled."""
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": "root", "node_type": "Node", "node_name": "test"},
            raise_on_error=False,
        )
        assert result.is_error
        msg = str(result.content).lower()
        assert "not enabled" in msg or "toolset" in msg


# ---------------------------------------------------------------------------
# 4. tools/list_changed notification (issue #485)
# ---------------------------------------------------------------------------


class _ToolListChangedRecorder(MessageHandler):
    """Records ToolListChangedNotification receipts."""

    def __init__(self) -> None:
        self.count = 0
        self.received = asyncio.Event()

    async def on_tool_list_changed(
        self, message: mcp_types.ToolListChangedNotification
    ) -> None:
        self.count += 1
        self.received.set()


async def _wait_for(handler: _ToolListChangedRecorder, timeout: float = 5.0) -> None:
    """Wait deterministically for the notification event (no sleep-waits)."""
    await asyncio.wait_for(handler.received.wait(), timeout=timeout)


async def test_enable_toolset_sends_list_changed_notification() -> None:
    """Enabling a toolset sends a tools/list_changed notification to the client."""
    server, _ = _build()
    handler = _ToolListChangedRecorder()
    async with Client(server, mode="legacy", message_handler=handler) as client:
        assert handler.count == 0
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await _wait_for(handler)
    assert handler.count >= 1


async def test_disable_toolset_sends_list_changed_notification() -> None:
    """Disabling a toolset sends a tools/list_changed notification to the client."""
    server, _ = _build()
    handler = _ToolListChangedRecorder()
    async with Client(server, mode="legacy", message_handler=handler) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await _wait_for(handler)
        handler.count = 0  # reset after enable
        handler.received.clear()
        await client.call_tool("godot_disable_toolset", {"category": "scene_edit"})
        await _wait_for(handler)
    assert handler.count >= 1

