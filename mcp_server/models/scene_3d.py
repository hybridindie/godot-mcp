"""Typed results for 3D scene tools (issue #40)."""

from __future__ import annotations

from pydantic import BaseModel


class MeshInstanceResult(BaseModel):
    node_path: str
    mesh_type: str
    created: bool = False
    dry_run: bool = False


class CameraResult(BaseModel):
    node_path: str
    current: bool = False
    created: bool = False
    dry_run: bool = False


class LightResult(BaseModel):
    node_path: str
    light_type: str
    created: bool = False
    dry_run: bool = False


class EnvironmentResult(BaseModel):
    node_path: str
    created: bool = False
    dry_run: bool = False


class GridMapCellResult(BaseModel):
    node_path: str
    position: list[int]
    item: int
    dry_run: bool = False
