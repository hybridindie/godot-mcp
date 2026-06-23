"""Typed results for 3D scene tools (issue #40)."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class GridMapCellGet(BaseModel):
    """A read of a GridMap cell (issue #219 G5) — inverts ``gridmap_set_cell``.
    ``item`` is the MeshLibrary index (-1 when empty); ``empty`` flags an unset cell."""

    node_path: str
    position: list[int] = Field(default_factory=list)
    item: int = -1
    orientation: int = 0
    empty: bool = True


class MeshLibraryResult(BaseModel):
    """Result of creating a MeshLibrary (issue #83). ``library_path`` is set when saved
    as a ``.tres``; ``node_path`` when assigned to a GridMap."""

    node_path: str = ""
    library_path: str = ""
    created: bool = False
    dry_run: bool = False


class MeshLibraryItemResult(BaseModel):
    """Result of adding an item to a MeshLibrary (issue #83). Exactly one of
    ``mesh_type`` (a primitive) or ``mesh_path`` (a Mesh resource) is set."""

    node_path: str = ""
    library_path: str = ""
    item_id: int = -1
    name: str = ""
    mesh_type: str = ""
    mesh_path: str = ""
    dry_run: bool = False
