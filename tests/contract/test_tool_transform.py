"""ToolTransform replaces the install_tool_naming monkeypatch (issue #312).

FastMCP 4.0's declarative ``ToolTransform`` renames tools as they flow from
providers to clients, with reverse-mapping on ``get_tool``. This guards that
the ``godot_<toolset>_<action>`` naming is applied via the transform (not via
wrapping ``mcp.tool``) and that clients can call tools by their public names.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.providers.base import Provider

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.transforms import _original_handler_name, godot_tool_name
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _build() -> FastMCP:
    config = ServerConfig()
    conn = FakeAddonConnection(make_addon_responder())
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge)


async def test_every_public_tool_is_godot_named() -> None:
    server = _build()
    # Provider.list_tools applies server-level transforms (the ToolTransform)
    # but skips the enabled filter, so ALL registered tools are visible here —
    # including toolset-gated ones — with their public godot_ names.
    tools = await Provider.list_tools(server)
    assert tools, "no tools registered"

    names: list[str] = []
    for tool in tools:
        names.append(tool.name)
        assert tool.name.startswith("godot_"), tool.name
        # The public name is exactly what the convention computes from the
        # handler + its tags — consistent by construction. The transform wraps
        # each tool in a TransformedTool (fn.__name__ == "_forward"), so the
        # original handler name is resolved via parent_tool.
        handler = _original_handler_name(tool)
        assert tool.name == godot_tool_name(handler, tool.tags), (handler, tool.name)

    assert len(names) == len(set(names)), "duplicate tool names"


async def test_reverse_mapping_routes_call_to_original_handler() -> None:
    server = _build()
    async with Client(server) as client:
        # The public godot_ name must route back to the original handler via
        # the transform's reverse map. cmd_get_project_info is handled by the
        # default make_addon_responder, so a successful (non-error) result
        # proves the routing reached the get_project_info handler.
        result = await client.call_tool("godot_inspection_get_project_info", {})
    sc = result.structured_content
    assert sc is not None
    assert sc["name"] == "TestProject"


async def test_mcp_tool_is_not_monkeypatched() -> None:
    server = _build()
    # The old install_tool_naming monkeypatch set `mcp.tool` as a per-instance
    # attribute shadowing the class descriptor. With the ToolTransform, `tool`
    # stays the class-level FastMCP decorator — no instance attribute shadows it.
    assert "tool" not in server.__dict__
    assert callable(getattr(FastMCP, "tool", None))