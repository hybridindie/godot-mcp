"""Contract tests for standard MCP tool annotations (issue #220).

Every tool carries a custom ``meta={"safety_class": ...}``; clients (e.g. Claude)
consume the *standard* MCP ``annotations`` (readOnlyHint / destructiveHint /
idempotentHint) instead. These tests pin that the standard annotations are
derived from ``safety_class`` for the whole tool surface — including toolset-gated
(disabled) tools, which the public ``list_tools()`` filters out.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.safety import apply_safety_annotations
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder
from tests.helpers import list_all_tools

pytestmark = pytest.mark.asyncio


def _server() -> FastMCP:
    config = ServerConfig()
    conn = FakeAddonConnection(make_addon_responder())
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge)


async def test_every_classified_tool_carries_annotations() -> None:
    server = _server()
    await apply_safety_annotations(server)
    # list_all_tools returns ALL registered tools (with server transforms applied),
    # including toolset-gated ones the public list_tools() filters out.
    tools = await list_all_tools(server)
    assert tools, "expected a non-empty tool surface"

    seen = {"read_only": 0, "mutating": 0, "destructive": 0, "runtime": 0}
    for tool in tools:
        safety_class = (tool.meta or {}).get("safety_class")
        if safety_class is None:
            continue
        seen[safety_class] = seen.get(safety_class, 0) + 1
        ann = tool.annotations
        assert ann is not None, f"{tool.name} ({safety_class}) has no MCP annotations"

        if safety_class == "read_only":
            assert ann.read_only_hint is True, tool.name
            assert ann.idempotent_hint is True, tool.name
        elif safety_class == "destructive":
            assert ann.read_only_hint is False, tool.name
            assert ann.destructive_hint is True, tool.name
        elif safety_class in ("mutating", "runtime"):
            assert ann.read_only_hint is False, tool.name
            assert ann.destructive_hint is False, tool.name

    # Make sure the assertions above actually ran for each class.
    assert seen["read_only"] > 0
    assert seen["mutating"] > 0
    assert seen["destructive"] > 0
    assert seen["runtime"] > 0


async def test_annotations_visible_on_public_surface() -> None:
    # The default-exposed read-only tools must surface readOnlyHint to clients.
    server = _server()
    from fastmcp import Client

    async with Client(server) as client:
        tools = {t.name: t for t in await client.list_tools()}

    health = tools["godot_health_check"]
    assert health.annotations is not None
    assert health.annotations.read_only_hint is True
