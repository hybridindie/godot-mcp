"""Contract test for the get_domain_vocabulary tool (issue #7)."""

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


async def test_get_domain_vocabulary_is_read_only_and_complete() -> None:
    async with Client(_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
        assert tools["get_domain_vocabulary"].meta["safety_class"] == "read_only"
        result = await client.call_tool("get_domain_vocabulary", {})

    vocab = result.structured_content
    assert "archer" in vocab["tower_archetypes"]
    assert "boss" in vocab["enemy_archetypes"]
    assert "double_speed" in vocab["wave_modifiers"]
    assert "in_progress" in vocab["run_states"]
