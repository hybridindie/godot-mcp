"""TileMap tools (issue #45).

Edit tile cells over the bridge: set a cell, fill a rectangle, read a cell, clear a
layer, and list layers. Works with both ``TileMapLayer`` (current; single layer, the
``layer`` arg is ignored) and the deprecated multi-layer ``TileMap`` (``layer`` selects
the layer). Gated `tilemap` toolset. Reads are `read_only`; edits are `mutating`
(UndoRedo-wrapped addon-side) with `dry_run`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import TILEMAP_TAG
from mcp_server.models.tilemap import (
    TileCellResult,
    TileClearResult,
    TileCreateResult,
    TileFillResult,
    TileGetResult,
    TileLayersResult,
    TileSetResult,
    TileSetSourceResult,
)
from mcp_server.safety import (
    MUTATING,
    READ_ONLY,
    PreconditionError,
    enforce_preconditions,
    require_node_exists,
)
from mcp_server.tools._route import route, run_or_preview

TILEMAP = {TILEMAP_TAG}


def _require_single_tileset_target(node_path: str, tileset_path: str) -> None:
    """A TileSet is targeted by exactly one of an in-scene node or a saved ``.tres``;
    reject both-set (ambiguous backing) and neither-set."""
    if node_path and tileset_path:
        raise PreconditionError(
            "Pass only one of 'node_path' or 'tileset_path', not both.",
            required="single_tileset_target",
        )
    if not node_path and not tileset_path:
        raise PreconditionError(
            "Provide 'node_path' (a TileMap/TileMapLayer) or 'tileset_path' (a .tres).",
            required="node_path_or_tileset_path",
        )


def register_tilemap(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the tilemap tools."""

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def tilemap_set_cell(
        node_path: str,
        coords: list[int],
        source_id: int = -1,
        atlas_coords: list[int] | None = None,
        alternative_tile: int = 0,
        layer: int = 0,
        dry_run: bool = False,
    ) -> TileCellResult:
        """Set the tile at grid ``coords`` ``[x, y]`` to ``source_id`` +
        ``atlas_coords`` ``[x, y]`` (default ``[0, 0]``) + ``alternative_tile``.
        ``source_id=-1`` erases the cell. ``layer`` applies to multi-layer TileMap only.
        """
        await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "coords": coords,
            "source_id": source_id,
            "atlas_coords": atlas_coords if atlas_coords is not None else [0, 0],
            "alternative_tile": alternative_tile,
            "layer": layer,
        }
        preview = {
            "node_path": node_path,
            "coords": coords,
            "source_id": source_id,
            "layer": layer,
        }
        return await run_or_preview(
            dry_run, TileCellResult, preview, bridge, "cmd_tilemap_set_cell", params
        )

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def tilemap_fill_rect(
        node_path: str,
        rect: list[int],
        source_id: int = -1,
        atlas_coords: list[int] | None = None,
        alternative_tile: int = 0,
        layer: int = 0,
        dry_run: bool = False,
    ) -> TileFillResult:
        """Fill the rectangle ``rect`` ``[x, y, w, h]`` of cells with the same tile
        (``source_id`` + ``atlas_coords`` + ``alternative_tile``; ``source_id=-1``
        erases). One undoable action. ``layer`` applies to multi-layer TileMap only.
        """
        await require_node_exists(bridge, node_path)
        cells = max(0, rect[2]) * max(0, rect[3]) if len(rect) == 4 else 0
        params = {
            "node_path": node_path,
            "rect": rect,
            "source_id": source_id,
            "atlas_coords": atlas_coords if atlas_coords is not None else [0, 0],
            "alternative_tile": alternative_tile,
            "layer": layer,
        }
        preview = {
            "node_path": node_path,
            "rect": rect,
            "cells": cells,
            "layer": layer,
        }
        return await run_or_preview(
            dry_run, TileFillResult, preview, bridge, "cmd_tilemap_fill_rect", params
        )

    @mcp.tool(meta=READ_ONLY, tags=TILEMAP)
    async def tilemap_get_cell(node_path: str, coords: list[int], layer: int = 0) -> TileGetResult:
        """Read the tile at grid ``coords`` ``[x, y]``: returns ``source_id``,
        ``atlas_coords``, ``alternative_tile``, and ``empty`` (true when no tile).
        ``layer`` applies to multi-layer TileMap only. Errors (RESOURCE_NOT_FOUND /
        PRECONDITION_FAILED) flow up from the addon as a structured ToolError.
        """
        params = {"node_path": node_path, "coords": coords, "layer": layer}
        return TileGetResult(**await route(bridge, "cmd_tilemap_get_cell", params))

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def tilemap_clear(
        node_path: str, layer: int | None = None, dry_run: bool = False
    ) -> TileClearResult:
        """Clear a layer's cells: for a multi-layer TileMap the given ``layer`` (default
        0), for a TileMapLayer the whole node. Undoable — the prior cells are restored
        on undo. Returns how many cells were cleared.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "layer": layer}
        preview = {"node_path": node_path, "layer": layer}
        return await run_or_preview(
            dry_run, TileClearResult, preview, bridge, "cmd_tilemap_clear", params
        )

    @mcp.tool(meta=READ_ONLY, tags=TILEMAP)
    async def tilemap_layers(node_path: str) -> TileLayersResult:
        """List the layers of the TileMap/TileMapLayer at ``node_path``: each layer's
        index, name, and enabled flag (a TileMapLayer reports its single layer).
        Errors flow up from the addon as a structured ToolError.
        """
        params = {"node_path": node_path}
        return TileLayersResult(**await route(bridge, "cmd_tilemap_layers", params))

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def create_tileset(
        node_path: str = "",
        save_path: str = "",
        tile_size: list[int] | None = None,
        dry_run: bool = False,
    ) -> TileSetResult:
        """Create a new TileSet resource — the prerequisite for placing real tiles with
        tilemap_set_cell. Assign it to a TileMap/TileMapLayer via ``node_path`` and/or
        persist it as a ``.tres`` via ``save_path`` (a ``res://`` path); pass at least
        one. ``tile_size`` ``[w, h]`` is the grid cell size (default ``[16, 16]``). Next
        add an atlas source with add_tileset_atlas_source.
        """
        size = tile_size if tile_size is not None else [16, 16]
        if not node_path and not save_path:
            raise PreconditionError(
                "Provide 'node_path' to assign the TileSet and/or 'save_path' to save it.",
                required="node_path_or_save_path",
            )
        if node_path:
            await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "save_path": save_path, "tile_size": size}
        preview = {"node_path": node_path, "tileset_path": save_path, "tile_size": size}
        return await run_or_preview(
            dry_run, TileSetResult, preview, bridge, "cmd_create_tileset", params
        )

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def add_tileset_atlas_source(
        texture_path: str,
        region_size: list[int],
        node_path: str = "",
        tileset_path: str = "",
        source_id: int | None = None,
        dry_run: bool = False,
    ) -> TileSetSourceResult:
        """Add an atlas source (a texture sliced into a tile grid) to a TileSet, then
        return its ``source_id`` (used by create_tile and tilemap_set_cell). Target the
        TileSet by ``node_path`` (an in-scene TileMap/TileMapLayer) or ``tileset_path``
        (a saved ``.tres``); pass exactly one. ``texture_path`` is the path (usually
        ``res://``) to an already imported Texture2D. ``region_size`` ``[w, h]`` is each
        tile's pixel size in the atlas. ``source_id`` overrides the auto-assigned id.
        """
        _require_single_tileset_target(node_path, tileset_path)
        if node_path:
            await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "tileset_path": tileset_path,
            "texture_path": texture_path,
            "region_size": region_size,
            "source_id": source_id,
        }
        preview = {
            "node_path": node_path,
            "tileset_path": tileset_path,
            "source_id": source_id if source_id is not None else -1,
            "texture_path": texture_path,
            "region_size": region_size,
        }
        return await run_or_preview(
            dry_run,
            TileSetSourceResult,
            preview,
            bridge,
            "cmd_add_tileset_atlas_source",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=TILEMAP)
    @enforce_preconditions
    async def create_tile(
        source_id: int,
        atlas_coords: list[int],
        node_path: str = "",
        tileset_path: str = "",
        size: list[int] | None = None,
        dry_run: bool = False,
    ) -> TileCreateResult:
        """Create a tile at ``atlas_coords`` ``[x, y]`` in atlas ``source_id`` of a
        TileSet, making that cell placeable with tilemap_set_cell. Target the TileSet by
        ``node_path`` (an in-scene TileMap/TileMapLayer) or ``tileset_path`` (a saved
        ``.tres``); pass exactly one. ``size`` ``[w, h]`` (in grid cells, default
        ``[1, 1]``) spans a multi-cell tile. Fails if the region is out of the atlas or
        overlaps an existing tile.
        """
        tile_size = size if size is not None else [1, 1]
        _require_single_tileset_target(node_path, tileset_path)
        if node_path:
            await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "tileset_path": tileset_path,
            "source_id": source_id,
            "atlas_coords": atlas_coords,
            "size": tile_size,
        }
        preview = {
            "node_path": node_path,
            "tileset_path": tileset_path,
            "source_id": source_id,
            "atlas_coords": atlas_coords,
            "size": tile_size,
        }
        return await run_or_preview(
            dry_run, TileCreateResult, preview, bridge, "cmd_create_tile", params
        )
