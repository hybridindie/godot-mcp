"""Typed results for tilemap tools (issue #45)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TileCellResult(BaseModel):
    node_path: str
    coords: list[int]
    source_id: int
    layer: int = 0
    dry_run: bool = False


class TileFillResult(BaseModel):
    node_path: str
    rect: list[int]
    cells: int = 0
    layer: int = 0
    dry_run: bool = False


class TileGetResult(BaseModel):
    node_path: str
    coords: list[int]
    source_id: int = -1
    atlas_coords: list[int] = Field(default_factory=lambda: [-1, -1])
    alternative_tile: int = -1
    empty: bool = True


class TileCellSnapshot(BaseModel):
    """One painted cell in a used-cells snapshot (issue #219 P3)."""

    coords: list[int]
    source_id: int = -1
    atlas_coords: list[int] = Field(default_factory=lambda: [-1, -1])
    alternative_tile: int = -1


class TileUsedCellsResult(BaseModel):
    """Bulk snapshot of a TileMap layer's painted cells (issue #219 P3) — the inverse
    of ``tilemap_fill_rect`` / ``tilemap_clear`` without per-cell reads."""

    node_path: str
    layer: int = 0
    count: int = 0
    cells: list[TileCellSnapshot] = Field(default_factory=list)


class TileClearResult(BaseModel):
    node_path: str
    layer: int | None = None
    cleared: int = 0
    dry_run: bool = False


class TileLayerInfo(BaseModel):
    index: int
    name: str
    enabled: bool = True


class TileLayersResult(BaseModel):
    node_path: str
    node_type: str
    layers: list[TileLayerInfo] = Field(default_factory=list)


class TileSetResult(BaseModel):
    """Result of creating a TileSet (issue #82). ``tileset_path`` is set when saved
    as a ``.tres``; ``node_path`` when assigned to a TileMap/TileMapLayer."""

    node_path: str = ""
    tileset_path: str = ""
    tile_size: list[int] = Field(default_factory=lambda: [16, 16])
    created: bool = True
    dry_run: bool = False


class TileSetSourceResult(BaseModel):
    """Result of adding an atlas source to a TileSet (issue #82)."""

    node_path: str = ""
    tileset_path: str = ""
    source_id: int = -1
    texture_path: str = ""
    region_size: list[int] = Field(default_factory=lambda: [16, 16])
    dry_run: bool = False


class TileCreateResult(BaseModel):
    """Result of creating a tile in an atlas source (issue #82)."""

    node_path: str = ""
    tileset_path: str = ""
    source_id: int = -1
    atlas_coords: list[int] = Field(default_factory=lambda: [0, 0])
    size: list[int] = Field(default_factory=lambda: [1, 1])
    dry_run: bool = False
