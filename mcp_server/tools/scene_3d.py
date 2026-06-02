"""3D scene tools (issue #40).

Build 3D scenes over the bridge: instance meshes, set up cameras/lights, configure
a WorldEnvironment, and paint GridMap cells. Gated `scene_3d` toolset; all
`mutating` (UndoRedo-wrapped addon-side) with `dry_run`. Generic Godot — pass the
node/resource type names (e.g. ``BoxMesh``, ``DirectionalLight3D``).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SCENE_3D_TAG
from mcp_server.models.scene_3d import (
    CameraResult,
    EnvironmentResult,
    GridMapCellResult,
    LightResult,
    MeshInstanceResult,
)
from mcp_server.safety import MUTATING, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

SCENE_3D = {SCENE_3D_TAG}


def register_scene_3d(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the 3D scene tools."""

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def add_mesh_instance(
        parent_path: str,
        mesh_type: str = "BoxMesh",
        name: str = "MeshInstance3D",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> MeshInstanceResult:
        """Add a MeshInstance3D under ``parent_path`` holding a ``mesh_type`` primitive
        mesh (e.g. BoxMesh, SphereMesh, CylinderMesh) configured with ``properties``
        (e.g. ``size``, ``radius``). Returns the new node's scene-relative path.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return MeshInstanceResult(
                node_path="", mesh_type=mesh_type, created=False, dry_run=True
            )
        params = {
            "parent_path": parent_path,
            "mesh_type": mesh_type,
            "name": name,
            "properties": properties or {},
        }
        return MeshInstanceResult(**await route(bridge, "cmd_add_mesh_instance", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_camera(
        parent_path: str,
        name: str = "Camera3D",
        make_current: bool = True,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> CameraResult:
        """Add a Camera3D under ``parent_path``, optionally ``make_current``, with
        ``properties`` such as ``fov``, ``near``, ``far``, ``position``.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return CameraResult(node_path="", current=make_current, created=False, dry_run=True)
        params = {
            "parent_path": parent_path,
            "name": name,
            "make_current": make_current,
            "properties": properties or {},
        }
        return CameraResult(**await route(bridge, "cmd_setup_camera", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_lighting(
        parent_path: str,
        light_type: str = "DirectionalLight3D",
        name: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> LightResult:
        """Add a 3D light under ``parent_path``: ``light_type`` is one of
        DirectionalLight3D / OmniLight3D / SpotLight3D, configured with ``properties``
        (e.g. ``light_color``, ``light_energy``, ``spot_angle``).
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return LightResult(node_path="", light_type=light_type, created=False, dry_run=True)
        params = {
            "parent_path": parent_path,
            "light_type": light_type,
            "name": name or light_type,
            "properties": properties or {},
        }
        return LightResult(**await route(bridge, "cmd_setup_lighting", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_environment(
        parent_path: str,
        name: str = "WorldEnvironment",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> EnvironmentResult:
        """Add a WorldEnvironment under ``parent_path`` with a new Environment resource
        configured via ``properties`` (e.g. ``background_mode``, ``ambient_light_color``,
        ``ambient_light_energy``, ``glow_enabled``).
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return EnvironmentResult(node_path="", created=False, dry_run=True)
        params = {
            "parent_path": parent_path,
            "name": name,
            "properties": properties or {},
        }
        return EnvironmentResult(**await route(bridge, "cmd_setup_environment", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def gridmap_set_cell(
        node_path: str,
        position: list[int],
        item: int,
        orientation: int = 0,
        dry_run: bool = False,
    ) -> GridMapCellResult:
        """Set a GridMap cell at the integer grid ``position`` ``[x, y, z]`` to mesh
        library index ``item`` (negative clears the cell), with optional ``orientation``.
        The node at ``node_path`` must be a GridMap with a ``mesh_library``.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return GridMapCellResult(
                node_path=node_path, position=position, item=item, dry_run=True
            )
        params = {
            "node_path": node_path,
            "position": position,
            "item": item,
            "orientation": orientation,
        }
        return GridMapCellResult(**await route(bridge, "cmd_gridmap_set_cell", params))
