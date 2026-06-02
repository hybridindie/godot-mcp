"""Contract tests for toolset gating (issue #26)."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _server() -> FastMCP:
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(config, bridge=bridge)


async def _tool_names(client: Client[Any]) -> set[str]:
    return {t.name for t in await client.list_tools()}


async def test_default_surface_is_core_plus_inspection() -> None:
    async with Client(_server()) as client:
        names = await _tool_names(client)
    # core + inspection exposed by default...
    assert {"health_check", "list_toolsets", "enable_toolset", "get_scene_tree"} <= names
    # ...but scene_edit (mutations) are gated off.
    assert "create_node" not in names
    assert "delete_node" not in names


async def test_enable_toolset_exposes_scene_edit() -> None:
    async with Client(_server()) as client:
        before = await _tool_names(client)
        assert "create_node" not in before
        result = await client.call_tool("enable_toolset", {"category": "scene_edit"})
        assert result.structured_content["enabled"] is True
        after = await _tool_names(client)
    assert "create_node" in after and "save_scene" in after


async def test_disable_toolset_hides_inspection_again() -> None:
    async with Client(_server()) as client:
        assert "get_scene_tree" in await _tool_names(client)
        await client.call_tool("disable_toolset", {"category": "inspection"})
        names = await _tool_names(client)
    assert "get_scene_tree" not in names
    assert "health_check" in names  # core stays


async def test_list_toolsets_reports_state() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("list_toolsets", {})
    by_name = {t["name"]: t for t in result.structured_content["result"]}
    assert by_name["inspection"]["enabled"] is True
    assert by_name["scene_edit"]["enabled"] is False
    assert by_name["core"]["enabled"] is True


async def test_unknown_toolset_is_structured_error() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool(
            "enable_toolset", {"category": "no_such_toolset"}, raise_on_error=False
        )
    assert result.is_error
    assert "Unknown toolset" in str(result.content)


async def test_core_cannot_be_toggled() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool(
            "disable_toolset", {"category": "core"}, raise_on_error=False
        )
    assert result.is_error
    assert "core" in str(result.content)
