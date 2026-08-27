"""Contract test for the list_tools_by_safety_class introspection tool (issue #14)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _server() -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(ServerConfig(), bridge=bridge)


async def test_list_tools_by_safety_class_tool() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("godot_list_tools_by_safety_class", {})
    grouped = result.structured_content["tools_by_safety_class"]

    # Every tool to date is read_only — including the introspection tool itself.
    read_only = set(grouped["read_only"])
    expected = {
        "godot_health_check",
        "godot_inspection_get_project_info",
        "godot_inspection_get_active_scene",
        "godot_inspection_get_scene_tree",
        "godot_inspection_get_selected_node",
        "godot_inspection_get_node_properties",
        "godot_list_tools_by_safety_class",
    }
    assert expected <= read_only
    # Nothing should be unclassified — every tool carries a safety Class.
    assert "unclassified" not in grouped


async def test_every_tool_has_a_safety_class() -> None:
    async with Client(_server()) as client:
        tools = await client.list_tools()
    for tool in tools:
        assert tool.meta is not None and tool.meta.get("safety_class"), (
            f"tool {tool.name} is missing a safety_class"
        )
