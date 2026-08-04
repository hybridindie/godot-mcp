"""Shared test helpers.

Centralizes the few FastMCP internals the suite still needs so a future
internals shift is a one-line fix here rather than a sweep across N files.

Specifically: enumerating *all* registered tools (including toolset-gated /
disabled ones) is required by several contract tests. FastMCP's public
``mcp.list_tools()`` filters out disabled tools; the public
``mcp.local_provider.list_tools()`` returns the full set (filtering happens at
the server level, not the provider level — see FastMCP 4.0 ``LocalProvider``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def list_all_tools(mcp: FastMCP) -> list[Any]:
    """Return every registered tool, including toolset-gated (disabled) ones.

    Uses the public ``FastMCP.local_provider`` surface (FastMCP 4.0): the local
    provider's ``list_tools()`` returns the unfiltered set; the server-level
    ``FastMCP.list_tools()`` is what applies the enabled/disabled filter.
    """
    return list(await mcp.local_provider.list_tools())
