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
