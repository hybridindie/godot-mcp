"""Integration tests for the bridge listener's peer lifecycle (issue #3, #276).

The MCP server is the listener now; the Godot addon is the client that connects and
*reconnects*. These verify the server side of that: a fresh peer (the addon reconnecting)
replaces the previous one, and a send with no peer is a structured error — no sockets,
no editor.
"""

from __future__ import annotations

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import ErrorCode
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


async def test_new_peer_replaces_the_previous_one() -> None:
    # The editor disconnects and reconnects: the second connection becomes the active
    # peer and the first is closed. (`connect()` attaches the connector's peer.)
    first = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(first))
    await bridge.connect()
    assert bridge.connected is True
    assert await bridge.ping() is True

    second = FakeAddonConnection()
    bridge._connector = connector_for(second)  # the addon reconnecting with a fresh peer
    await bridge.connect()

    assert first.closed is True  # old peer dropped
    assert bridge.connected is True
    assert await bridge.ping() is True  # serviced by the new peer
    await bridge.close()


async def test_send_without_a_peer_is_structured_error() -> None:
    # Listener up, no editor connected ⇒ a structured BRIDGE_DISCONNECTED, never a raise.
    bridge = Bridge(BridgeConfig())
    resp = await bridge.send("cmd_ping")
    assert resp.ok is False
    assert resp.error == ErrorCode.BRIDGE_DISCONNECTED
