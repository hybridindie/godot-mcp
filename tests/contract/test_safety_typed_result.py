"""Contract: list_tools_by_safety_class returns a typed Pydantic model (issue #366).

The tool previously returned a raw ``dict[str, list[str]]``, violating
``.opencode/rules/mcp-tools.md`` ("return a typed Pydantic model — never a
raw ``dict``"). It now returns a :class:`SafetyClassListing` model with one
field ``tools_by_safety_class``.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.safety import SafetyClassListing
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _server() -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(ServerConfig(), bridge=bridge)


async def test_returns_typed_model_shape() -> None:
    """The tool result is a SafetyClassListing — a single-field model, not a
    flat dict. The structured content carries the ``tools_by_safety_class`` key."""
    async with Client(_server()) as client:
        result = await client.call_tool("godot_list_tools_by_safety_class", {})
    grouped = result.structured_content
    # The new shape wraps under one key (the Pydantic model's field name).
    assert "tools_by_safety_class" in grouped
    by_class = grouped["tools_by_safety_class"]
    assert isinstance(by_class, dict)
    # read_only tools are present.
    assert "read_only" in by_class
    assert "godot_health_check" in by_class["read_only"]


async def test_model_round_trips() -> None:
    """The Pydantic model round-trips the data faithfully."""
    async with Client(_server()) as client:
        result = await client.call_tool("godot_list_tools_by_safety_class", {})
    listing = SafetyClassListing.model_validate(result.structured_content)
    assert "read_only" in listing.tools_by_safety_class
    assert "godot_health_check" in listing.tools_by_safety_class["read_only"]
    assert "unclassified" not in listing.tools_by_safety_class