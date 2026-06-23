"""Contract tests: numeric tool inputs carry Pydantic Field bounds (issue #221).

Unbounded numeric params deferred all validation to the addon. These tests pin
that the resource/safety-relevant numeric params declare a lower bound (and, where
meaningful, an upper bound) in the JSON schema the agent sees — across the whole
tool surface, including toolset-gated tools.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.server import create_server

# Params that must be bounded wherever they appear (a lower bound at minimum).
BOUNDED_PARAMS = {
    "samples",
    "max_depth",
    "timeout_seconds",
    "timeout_ms",
    "max_results",
    "delay_ms",
    "setup_ms",
    "settle_ms",
    "iterations",
    "amount",
    "source_id",
    "layer",
    "alternative_tile",
}


def _numeric_leaf_has_minimum(schema: dict[str, Any]) -> bool:
    """A numeric param schema declares a minimum, allowing for ``int | None`` (anyOf)."""
    candidates = [schema, *schema.get("anyOf", [])]
    numeric = [c for c in candidates if c.get("type") in ("integer", "number")]
    if not numeric:
        return True  # not a numeric leaf — not our concern
    return all("minimum" in c for c in numeric)


def test_targeted_numeric_params_declare_bounds() -> None:
    server = create_server()
    import asyncio

    tools = asyncio.run(server._list_tools())
    unbounded: list[str] = []
    checked = 0
    for tool in tools:
        props = (tool.parameters or {}).get("properties", {})
        for name, schema in props.items():
            if name not in BOUNDED_PARAMS:
                continue
            checked += 1
            if not _numeric_leaf_has_minimum(schema):
                unbounded.append(f"{tool.name}.{name}")
    assert checked > 0, "no targeted params found — test wiring is broken"
    assert not unbounded, f"unbounded numeric params: {sorted(unbounded)}"


async def test_out_of_range_rejected_before_bridge() -> None:
    # get_scene_tree is in the default-on `inspection` toolset; an out-of-range
    # max_depth must be rejected by the server schema, not sent to the addon.
    server: FastMCP = create_server()
    async with Client(server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_scene_tree", {"max_depth": -5})
