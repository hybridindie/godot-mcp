"""Contract tests: bounded read outputs — pagination + char cap (issue #222).

List-shaped tools (find_nodes_by_type, list_scripts) paginate with limit/offset and
report total/truncated/next_offset. Large reads (the scene tree) are capped at a
character limit with an explicit truncation marker so they can't blow up context.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.output import CHARACTER_LIMIT
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, _default_base_responder, connector_for

pytestmark = pytest.mark.asyncio


def _big_tree() -> dict[str, Any]:
    children: list[dict[str, Any]] = [
        {"name": f"Node{i}", "type": "Sprite2D", "path": f"Root/Node{i}", "script": None,
         "children": []}
        for i in range(700)
    ]
    return {"name": "Root", "type": "Node2D", "path": ".", "script": None, "children": children}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope:
    base = _default_base_responder(cmd)
    if base is not None:
        return base
    if cmd.command == "cmd_find_nodes_by_type":
        nodes = [{"path": f"Root/N{i}", "name": f"N{i}", "type": "Sprite2D"} for i in range(10)]
        return ResponseEnvelope.success(cmd.id, {"type": "Sprite2D", "nodes": nodes, "count": 10})
    if cmd.command == "cmd_list_scripts":
        scripts = [f"res://s{i}.gd" for i in range(10)]
        return ResponseEnvelope.success(cmd.id, {"directory": "res://", "scripts": scripts})
    if cmd.command == "cmd_get_scene_tree":
        if cmd.params.get("lightweight"):
            return ResponseEnvelope.success(
                cmd.id, {"tree": {"name": "Root", "type": "Node2D", "path": ".", "children": []}}
            )
        return ResponseEnvelope.success(cmd.id, {"tree": _big_tree()})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", f"unknown {cmd.command}")


def _server() -> FastMCP:
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection(_responder)))
    return create_server(config, bridge=bridge)


async def test_find_nodes_by_type_paginates() -> None:
    async with Client(_server()) as client:
        await client.call_tool("enable_toolset", {"category": "batch"})
        result = await client.call_tool(
            "find_nodes_by_type", {"node_type": "Sprite2D", "limit": 3, "offset": 0}
        )
    data = result.data
    assert len(data.nodes) == 3
    assert data.total == 10
    assert data.truncated is True
    assert data.next_offset == 3


async def test_list_scripts_paginates_last_page() -> None:
    async with Client(_server()) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        result = await client.call_tool("list_scripts", {"limit": 4, "offset": 8})
    data = result.data
    assert len(data.scripts) == 2
    assert data.total == 10
    assert data.truncated is False
    assert data.next_offset is None


async def test_scene_tree_resource_is_char_capped() -> None:
    async with Client(_server()) as client:
        contents = await client.read_resource("godot://scene/tree")
    text = contents[0].text
    assert len(text) <= CHARACTER_LIMIT + 500  # marker, not the giant tree
    assert json.loads(text)["truncated"] is True


async def test_get_scene_tree_tool_marks_truncation() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("get_scene_tree", {})
    assert result.data.truncated is True
    assert result.data.hint
