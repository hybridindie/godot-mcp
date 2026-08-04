"""Shared test helpers.

``list_all_tools`` is the transform-aware replacement for ``server._list_tools()``:
it applies the server-level ``ToolTransform`` (so tools carry their public
``godot_`` names) but skips the enabled filter, yielding the *full* registered
surface — including toolset-gated tools — for contract checks that must cover
every tool, not just the default-exposed ones (issue #313/#324).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.providers.base import Provider
from fastmcp.tools.base import Tool


async def list_all_tools(server: FastMCP) -> list[Tool]:
    """All registered tools with server-level transforms applied (no enabled filter)."""
    return list(await Provider.list_tools(server))


__all__ = ["list_all_tools"]