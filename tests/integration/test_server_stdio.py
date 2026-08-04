"""Integration test: the server starts over real stdio and lists its tool (issue #4).

Spawns the actual entrypoint as a subprocess (``python -m mcp_server.main``) and
drives it with a real MCP stdio client — the automated form of the acceptance
criteria "starts without errors" and "client can list at least one tool". Needs
no Godot (the bridge simply reports disconnected), so it runs in CI.
"""

from __future__ import annotations

import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

pytestmark = pytest.mark.asyncio


def _entrypoint_transport() -> StdioTransport:
    # Use the current interpreter and the module entrypoint (absolute imports mean
    # `python -m mcp_server.main`, not running the file path directly).
    return StdioTransport(command=sys.executable, args=["-m", "mcp_server.main"])


async def test_stdio_server_lists_health_check() -> None:
    async with Client(_entrypoint_transport()) as client:
        tools = await client.list_tools()
    assert "godot_health_check" in {t.name for t in tools}


async def test_stdio_server_health_check_callable() -> None:
    async with Client(_entrypoint_transport()) as client:
        result = await client.call_tool("godot_health_check", {})
    payload = result.structured_content
    assert payload["server"] == "godot-mcp"
    # No editor running under this test ⇒ bridge reports disconnected, not an error.
    assert payload["bridge_connected"] is False
