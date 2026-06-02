"""Contract tests for tilemap tools (issue #45)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_node_properties":  # require_node_exists precondition
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "type": "TileMapLayer"}
            )
        case "cmd_tilemap_set_cell":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "coords": p["coords"],
                    "source_id": p["source_id"],
                    "layer": p["layer"],
                },
            )
        case "cmd_tilemap_fill_rect":
            r = p["rect"]
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "rect": r,
                    "cells": r[2] * r[3],
                    "layer": p["layer"],
                },
            )
        case "cmd_tilemap_get_cell":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "coords": p["coords"],
                    "source_id": -1,
                    "atlas_coords": [-1, -1],
                    "alternative_tile": -1,
                    "empty": True,
                },
            )
        case "cmd_tilemap_clear":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "layer": p["layer"], "cleared": 4}
            )
        case "cmd_tilemap_layers":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "node_type": "TileMapLayer",
                    "layers": [{"index": 0, "name": "Ground", "enabled": True}],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_tilemap_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "tilemap_set_cell" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        tools = {t.name: t for t in await client.list_tools()}
    mutating = {"tilemap_set_cell", "tilemap_fill_rect", "tilemap_clear"}
    read_only = {"tilemap_get_cell", "tilemap_layers"}
    assert (mutating | read_only) <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in mutating)
    assert all(tools[n].meta["safety_class"] == "read_only" for n in read_only)


async def test_set_cell_and_fill_rect() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        cell = await client.call_tool(
            "tilemap_set_cell",
            {"node_path": "Ground", "coords": [3, 4], "source_id": 0, "atlas_coords": [1, 2]},
        )
        fill = await client.call_tool(
            "tilemap_fill_rect",
            {"node_path": "Ground", "rect": [0, 0, 4, 3], "source_id": 0},
        )
    assert cell.structured_content["coords"] == [3, 4]
    assert cell.structured_content["source_id"] == 0
    assert fill.structured_content["cells"] == 12


async def test_get_cell_and_layers() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        cell = await client.call_tool("tilemap_get_cell", {"node_path": "Ground", "coords": [0, 0]})
        layers = await client.call_tool("tilemap_layers", {"node_path": "Ground"})
    assert cell.structured_content["empty"] is True
    assert cell.structured_content["source_id"] == -1
    assert layers.structured_content["node_type"] == "TileMapLayer"
    assert layers.structured_content["layers"][0]["name"] == "Ground"


async def test_clear_and_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        cleared = await client.call_tool("tilemap_clear", {"node_path": "Ground"})
        dry = await client.call_tool(
            "tilemap_set_cell",
            {"node_path": "Ground", "coords": [1, 1], "source_id": 0, "dry_run": True},
        )
    assert cleared.structured_content["cleared"] == 4
    assert dry.structured_content["dry_run"] is True
    assert "cmd_tilemap_set_cell" not in _commands(conn)
