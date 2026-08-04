"""Every MCP tool follows the godot_<toolset>_<action> convention (issue #224).

Guards the uniform naming installed by ``mcp_server.tool_naming`` against drift: a new
tool added without the convention (or a collision) fails here.
"""

from __future__ import annotations

import pytest

from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.tool_naming import _category, godot_tool_name
from tests.helpers import list_all_tools

pytestmark = pytest.mark.asyncio


async def test_every_tool_is_godot_named_and_consistent() -> None:
    mcp = create_server(ServerConfig())
    tools = await list_all_tools(mcp)
    assert tools, "no tools registered"

    names: list[str] = []
    for tool in tools:
        names.append(tool.name)
        # Uniform prefix.
        assert tool.name.startswith("godot_"), tool.name
        # Name is exactly what the convention computes from the handler + its tags —
        # i.e. consistent by construction, with no per-tool drift.
        handler = getattr(tool, "fn").__name__  # noqa: B009  (FunctionTool.fn, untyped on base Tool)
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
