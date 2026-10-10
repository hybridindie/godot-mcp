"""Contract tests: server-side ``subscriptions/listen`` wiring (issue #620).

On the sessionless MCP ``2026-07-28`` protocol there is no standing server→client
channel: the spec forbids unsolicited change notifications, so they reach a
client only on a ``subscriptions/listen`` stream it explicitly opens. FastMCP
drives the low-level mcp ``Server`` directly and never registered the method, so
on the modern era it advertised ``tools.listChanged: false`` — capable clients
(Claude Code CLI) therefore never subscribed. These tests pin the fix: the
modern handshake advertises the capability, and a real listen stream receives
``tools/list_changed`` after a toolset toggle.
"""

from __future__ import annotations

import asyncio

import mcp_types
import pytest
from fastmcp import Client, FastMCP
from mcp.client.subscriptions import listen
from mcp.shared.subscriptions import ToolsListChanged

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _build() -> FastMCP:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_modern_handshake_advertises_tools_list_changed() -> None:
    """The ``2026-07-28`` handshake must advertise ``tools.listChanged: true``.

    The mcp SDK derives that flag from whether ``subscriptions/listen`` is
    served; without it, subscription-gated clients stay disconnected from the
    gating feature entirely.
    """
    server = _build()
    async with Client(server, mode="2026-07-28") as client:
        assert client.protocol_version == "2026-07-28", client.protocol_version
        # On the modern era discovery is server/discover, not initialize. Read
        # the raw wire result (the advertisement real clients act on).
        raw = await client.session.send_discover("2026-07-28")
        capabilities = mcp_types.ServerCapabilities.model_validate(raw["capabilities"])
        tools_capability = capabilities.tools
        assert tools_capability is not None
        assert tools_capability.list_changed is True


async def test_listen_stream_receives_tools_list_changed_on_toggle() -> None:
    """A client that opens ``subscriptions/listen`` receives
    ``ToolsListChanged`` after ``godot_enable_toolset`` — the out-of-band path
    the modern protocol gives gating.
    """
    server = _build()
    async with Client(server, mode="2026-07-28") as client:
        async with listen(client.session, tools_list_changed=True) as subscription:
            await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})

            async def _first_tools_event() -> ToolsListChanged | None:
                async for event in subscription:
                    if isinstance(event, ToolsListChanged):
                        return event
                return None

            event = await asyncio.wait_for(_first_tools_event(), timeout=5.0)
            assert event is not None
