"""Typed results for navigation tools (issue #43)."""

from __future__ import annotations

from pydantic import BaseModel


class NavigationRegionResult(BaseModel):
    node_path: str
    region_type: str
    created: bool = False
    dry_run: bool = False


class NavigationAgentResult(BaseModel):
    node_path: str
    agent_type: str
    created: bool = False
    dry_run: bool = False


class BakeNavigationResult(BaseModel):
    node_path: str
    baked: bool = False
    # Only present on a real (non-dry-run) bake: the produced polygon/vertex
    # counts — a bake yielding 0 polygons is refused by the addon (#413).
    polygon_count: int | None = None
    vertex_count: int | None = None
    dry_run: bool = False


class NavigationLayersResult(BaseModel):
    node_path: str
    navigation_layers: int = 0
    dry_run: bool = False


class NavigationRegionInfo(BaseModel):
    node_path: str
    has_polygon: bool = False
    outline_count: int = 0
    vertex_count: int = 0
    polygon_count: int = 0
