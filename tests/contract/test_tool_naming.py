"""Every MCP tool follows the godot_<toolset>_<action> convention (issue #224).

Guards the uniform naming applied by ``mcp_server.transforms`` against drift: a
new tool added without the convention (or a collision) fails here.
"""

from __future__ import annotations

import pytest
from fastmcp.server.providers.base import Provider

from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.transforms import _category, _original_handler_name, godot_tool_name

pytestmark = pytest.mark.asyncio


async def test_every_tool_is_godot_named_and_consistent() -> None:
    mcp = create_server(ServerConfig())
    # Provider.list_tools applies the server-level ToolTransform (which renames
    # every tool to its godot_ form) but skips the enabled filter, so ALL
    # registered tools — including toolset-gated ones — are visible here.
    tools = await Provider.list_tools(mcp)
    assert tools, "no tools registered"

    names: list[str] = []
    for tool in tools:
        names.append(tool.name)
        # Uniform prefix.
        assert tool.name.startswith("godot_"), tool.name
        # Name is exactly what the convention computes from the handler + its tags —
        # i.e. consistent by construction, with no per-tool drift. The transform
        # wraps each tool in a TransformedTool (fn.__name__ == "_forward"), so the
        # original handler name is resolved via parent_tool.
        handler = _original_handler_name(tool)
        assert tool.name == godot_tool_name(handler, tool.tags), (handler, tool.name)
        # The prefix encodes the gating toolset (core/meta tools are just godot_<action>).
        cat = _category(tool.tags)
        if cat != CORE_TAG:
            assert tool.name.startswith(f"godot_{cat}_") or tool.name == f"godot_{cat}", (
                cat,
                tool.name,
            )

    # No collisions across the whole surface.
    assert len(names) == len(set(names)), "duplicate tool names"
