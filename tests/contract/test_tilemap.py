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
        case "cmd_create_tileset":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path", ""),
                    "tileset_path": p.get("save_path", ""),
                    "tile_size": p["tile_size"],
                    "created": True,
                },
            )
        case "cmd_add_tileset_atlas_source":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path", ""),
                    "tileset_path": p.get("tileset_path", ""),
                    "source_id": 0,
                    "texture_path": p["texture_path"],
                    "region_size": p["region_size"],
                },
            )
        case "cmd_create_tile":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path", ""),
                    "tileset_path": p.get("tileset_path", ""),
                    "source_id": p["source_id"],
                    "atlas_coords": p["atlas_coords"],
                    "size": p["size"],
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


async def test_readonly_tool_surfaces_structured_precondition() -> None:
    # get_cell is read_only (no @enforce_preconditions); a precondition envelope from
    # the addon must still reach the agent as a structured ToolError via route().
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_tilemap_get_cell":
            return ResponseEnvelope.failure(
                cmd.id, "PRECONDITION_FAILED", "No scene is open.", required="active_scene"
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        result = await client.call_tool(
            "tilemap_get_cell",
            {"node_path": "Ground", "coords": [0, 0]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "active_scene" in str(result.content)


async def test_tileset_authoring_chain() -> None:
    # Build a TileSet on a node, add an atlas source from a texture, and create a tile —
    # the prerequisite chain that lets tilemap_set_cell place real tiles.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        ts = await client.call_tool(
            "create_tileset", {"node_path": "Ground", "tile_size": [16, 16]}
        )
        src = await client.call_tool(
            "add_tileset_atlas_source",
            {"node_path": "Ground", "texture_path": "res://tiles.png", "region_size": [16, 16]},
        )
        tile = await client.call_tool(
            "create_tile", {"node_path": "Ground", "source_id": 0, "atlas_coords": [0, 0]},
        )
    assert ts.structured_content["tile_size"] == [16, 16]
    assert ts.structured_content["created"] is True
    assert src.structured_content["source_id"] == 0
    assert src.structured_content["texture_path"] == "res://tiles.png"
    assert tile.structured_content["atlas_coords"] == [0, 0]
    assert tile.structured_content["size"] == [1, 1]


async def test_tileset_authoring_file_backed_and_safety() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        tools = {t.name: t for t in await client.list_tools()}
        authoring = {"create_tileset", "add_tileset_atlas_source", "create_tile"}
        assert authoring <= set(tools)
        assert all(tools[n].meta["safety_class"] == "mutating" for n in authoring)
        # a .tres-backed source needs no node_path
        saved = await client.call_tool(
            "create_tileset", {"save_path": "res://floor.tres", "tile_size": [8, 8]}
        )
        src = await client.call_tool(
            "add_tileset_atlas_source",
            {
                "tileset_path": "res://floor.tres",
                "texture_path": "res://tiles.png",
                "region_size": [8, 8],
            },
        )
    assert saved.structured_content["tileset_path"] == "res://floor.tres"
    assert src.structured_content["tileset_path"] == "res://floor.tres"


async def test_tileset_create_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "tilemap"})
        dry = await client.call_tool(
            "create_tileset", {"save_path": "res://x.tres", "dry_run": True}
        )
    assert dry.structured_content["dry_run"] is True
    assert "cmd_create_tileset" not in _commands(conn)


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
