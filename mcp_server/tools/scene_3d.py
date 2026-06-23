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
from mcp_server.defaults import (
    DEFAULT_CAMERA_NAME,
    DEFAULT_GRIDMAP_ORIENTATION,
    DEFAULT_LIGHT_TYPE,
    DEFAULT_MESH_INSTANCE_NAME,
    DEFAULT_MESH_TYPE,
    DEFAULT_WORLD_ENVIRONMENT_NAME,
)
from mcp_server.models.scene_3d import (
    CameraResult,
    EnvironmentResult,
    GridMapCellGet,
    GridMapCellResult,
    LightResult,
    MeshInstanceResult,
    MeshLibraryItemResult,
    MeshLibraryResult,
)
from mcp_server.safety import (
    MUTATING,
    READ_ONLY,
    PreconditionError,
    enforce_preconditions,
    require_node_exists,
)
from mcp_server.tools._route import route, run_or_preview

SCENE_3D = {SCENE_3D_TAG}


def _require_single_library_target(node_path: str, library_path: str) -> None:
    """A MeshLibrary is targeted by exactly one of an in-scene GridMap or a saved
    ``.tres``; reject both-set (ambiguous backing) and neither-set."""
    if node_path and library_path:
        raise PreconditionError(
            "Pass only one of 'node_path' or 'library_path', not both.",
            required="single_library_target",
        )
    if not node_path and not library_path:
        raise PreconditionError(
            "Provide 'node_path' (a GridMap) or 'library_path' (a .tres).",
            required="node_path_or_library_path",
        )


def _require_single_mesh_source(mesh_type: str, mesh_path: str) -> None:
    """An item's mesh comes from exactly one of a primitive ``mesh_type`` or a
    ``mesh_path`` Mesh resource."""
    if mesh_type and mesh_path:
        raise PreconditionError(
            "Pass only one of 'mesh_type' or 'mesh_path', not both.",
            required="single_mesh_source",
        )
    if not mesh_type and not mesh_path:
        raise PreconditionError(
            "Provide 'mesh_type' (a primitive like BoxMesh) or 'mesh_path' (a Mesh resource).",
            required="mesh_type_or_mesh_path",
        )


def register_scene_3d(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the 3D scene tools."""

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def add_mesh_instance(
        parent_path: str,
        mesh_type: str = DEFAULT_MESH_TYPE,
        name: str = DEFAULT_MESH_INSTANCE_NAME,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> MeshInstanceResult:
        """Add a MeshInstance3D under ``parent_path`` holding a ``mesh_type`` primitive
        mesh (e.g. BoxMesh, SphereMesh, CylinderMesh) configured with ``properties``
        (e.g. ``size``, ``radius``). Returns the new node's scene-relative path.
        """
        await require_node_exists(bridge, parent_path)
        params = {
            "parent_path": parent_path,
            "mesh_type": mesh_type,
            "name": name,
            "properties": properties or {},
        }
        preview = {"node_path": "", "mesh_type": mesh_type, "created": False}
        return await run_or_preview(
            dry_run, MeshInstanceResult, preview, bridge, "cmd_add_mesh_instance", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_camera(
        parent_path: str,
        name: str = DEFAULT_CAMERA_NAME,
        make_current: bool = True,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> CameraResult:
        """Add a Camera3D under ``parent_path``, optionally ``make_current``, with
        ``properties`` such as ``fov``, ``near``, ``far``, ``position``.
        """
        await require_node_exists(bridge, parent_path)
        params = {
            "parent_path": parent_path,
            "name": name,
            "make_current": make_current,
            "properties": properties or {},
        }
        preview = {"node_path": "", "current": make_current, "created": False}
        return await run_or_preview(
            dry_run, CameraResult, preview, bridge, "cmd_setup_camera", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_lighting(
        parent_path: str,
        light_type: str = DEFAULT_LIGHT_TYPE,
        name: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> LightResult:
        """Add a 3D light under ``parent_path``: ``light_type`` is one of
        DirectionalLight3D / OmniLight3D / SpotLight3D, configured with ``properties``
        (e.g. ``light_color``, ``light_energy``, ``spot_angle``).
        """
        await require_node_exists(bridge, parent_path)
        params = {
            "parent_path": parent_path,
            "light_type": light_type,
            "name": name or light_type,
            "properties": properties or {},
        }
        preview = {"node_path": "", "light_type": light_type, "created": False}
        return await run_or_preview(
            dry_run, LightResult, preview, bridge, "cmd_setup_lighting", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def setup_environment(
        parent_path: str,
        name: str = DEFAULT_WORLD_ENVIRONMENT_NAME,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> EnvironmentResult:
        """Add a WorldEnvironment under ``parent_path`` with a new Environment resource
        configured via ``properties`` (e.g. ``background_mode``, ``ambient_light_color``,
        ``ambient_light_energy``, ``glow_enabled``).
        """
        await require_node_exists(bridge, parent_path)
        params = {
            "parent_path": parent_path,
            "name": name,
            "properties": properties or {},
        }
        preview = {"node_path": "", "created": False}
        return await run_or_preview(
            dry_run, EnvironmentResult, preview, bridge, "cmd_setup_environment", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def gridmap_set_cell(
        node_path: str,
        position: list[int],
        item: int,
        orientation: int = DEFAULT_GRIDMAP_ORIENTATION,
        dry_run: bool = False,
    ) -> GridMapCellResult:
        """Set a GridMap cell at the integer grid ``position`` ``[x, y, z]`` to mesh
        library index ``item`` (negative clears the cell), with optional ``orientation``.
        The node at ``node_path`` must be a GridMap with a ``mesh_library``.
        """
        await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "position": position,
            "item": item,
            "orientation": orientation,
        }
        preview = {"node_path": node_path, "position": position, "item": item}
        return await run_or_preview(
            dry_run, GridMapCellResult, preview, bridge, "cmd_gridmap_set_cell", params
        )

    @mcp.tool(meta=READ_ONLY, tags=SCENE_3D)
    async def gridmap_get_cell(node_path: str, position: list[int]) -> GridMapCellGet:
        """Read the GridMap cell at the integer grid ``position`` ``[x, y, z]``: its
        ``item`` (MeshLibrary index, -1 when empty), ``orientation``, and ``empty``.
        Symmetric with ``tilemap_get_cell`` and the inverse of ``gridmap_set_cell`` —
        snapshot a cell before changing it for rollback. Errors if the node isn't a
        GridMap or doesn't resolve.
        """
        params = {"node_path": node_path, "position": position}
        return GridMapCellGet(**await route(bridge, "cmd_gridmap_get_cell", params))

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def create_mesh_library(
        node_path: str = "",
        save_path: str = "",
        dry_run: bool = False,
    ) -> MeshLibraryResult:
        """Create a new MeshLibrary resource — the prerequisite for placing cells with
        gridmap_set_cell. Assign it to a GridMap via ``node_path`` and/or persist it as a
        ``.tres`` via ``save_path`` (a ``res://`` path); pass at least one. Next add items
        with add_mesh_library_item.
        """
        if not node_path and not save_path:
            raise PreconditionError(
                "Provide 'node_path' to assign the MeshLibrary and/or 'save_path' to save it.",
                required="node_path_or_save_path",
            )
        if node_path:
            await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "save_path": save_path}
        preview = {"node_path": node_path, "library_path": save_path}
        return await run_or_preview(
            dry_run, MeshLibraryResult, preview, bridge, "cmd_create_mesh_library", params
        )

    @mcp.tool(meta=MUTATING, tags=SCENE_3D)
    @enforce_preconditions
    async def add_mesh_library_item(
        node_path: str = "",
        library_path: str = "",
        mesh_type: str = "",
        mesh_path: str = "",
        item_id: int | None = None,
        name: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> MeshLibraryItemResult:
        """Add an item to a MeshLibrary and return its ``item_id`` (used by
        gridmap_set_cell). Target the MeshLibrary by ``node_path`` (an in-scene GridMap)
        or ``library_path`` (a saved ``.tres``); pass exactly one. The item's mesh comes
        from exactly one of ``mesh_type`` (a primitive like BoxMesh, configured with
        ``properties`` such as ``size``) or ``mesh_path`` (the path to an imported Mesh
        resource).
        """
        _require_single_library_target(node_path, library_path)
        _require_single_mesh_source(mesh_type, mesh_path)
        if node_path:
            await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "library_path": library_path,
            "mesh_type": mesh_type,
            "mesh_path": mesh_path,
            "item_id": item_id,
            "name": name,
            "properties": properties or {},
        }
        preview = {
            "node_path": node_path,
            "library_path": library_path,
            "item_id": item_id if item_id is not None else -1,
            "name": name,
            "mesh_type": mesh_type,
            "mesh_path": mesh_path,
        }
        return await run_or_preview(
            dry_run, MeshLibraryItemResult, preview, bridge, "cmd_add_mesh_library_item", params
        )
