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
    TileFillResult,
    TileGetResult,
    TileLayersResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

TILEMAP = {TILEMAP_TAG}


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
        if dry_run:
            return TileCellResult(
                node_path=node_path, coords=coords, source_id=source_id, layer=layer, dry_run=True
            )
        params = {
            "node_path": node_path,
            "coords": coords,
            "source_id": source_id,
            "atlas_coords": atlas_coords if atlas_coords is not None else [0, 0],
            "alternative_tile": alternative_tile,
            "layer": layer,
        }
        return TileCellResult(**await route(bridge, "cmd_tilemap_set_cell", params))

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
        if dry_run:
            cells = max(0, rect[2]) * max(0, rect[3]) if len(rect) == 4 else 0
            return TileFillResult(
                node_path=node_path, rect=rect, cells=cells, layer=layer, dry_run=True
            )
        params = {
            "node_path": node_path,
            "rect": rect,
            "source_id": source_id,
            "atlas_coords": atlas_coords if atlas_coords is not None else [0, 0],
            "alternative_tile": alternative_tile,
            "layer": layer,
        }
        return TileFillResult(**await route(bridge, "cmd_tilemap_fill_rect", params))

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
        if dry_run:
            return TileClearResult(node_path=node_path, layer=layer, dry_run=True)
        params = {"node_path": node_path, "layer": layer}
        return TileClearResult(**await route(bridge, "cmd_tilemap_clear", params))

    @mcp.tool(meta=READ_ONLY, tags=TILEMAP)
    async def tilemap_layers(node_path: str) -> TileLayersResult:
        """List the layers of the TileMap/TileMapLayer at ``node_path``: each layer's
        index, name, and enabled flag (a TileMapLayer reports its single layer).
        Errors flow up from the addon as a structured ToolError.
        """
        params = {"node_path": node_path}
        return TileLayersResult(**await route(bridge, "cmd_tilemap_layers", params))
