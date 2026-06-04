"""Physics tools (issue #41).

Configure physics bodies/areas, attach collision shapes, set collision layers/masks,
and add raycasts. Gated `physics` toolset; all `mutating` (UndoRedo-wrapped addon-side)
with `dry_run`. Generic over 2D/3D — pass the Godot type names (e.g. ``RectangleShape2D``
/ ``BoxShape3D``, ``CollisionShape2D`` / ``CollisionShape3D``, ``RayCast2D`` / ``RayCast3D``).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PHYSICS_TAG
from mcp_server.defaults import (
    DEFAULT_COLLISION_NODE_TYPE,
    DEFAULT_RAYCAST_NAME,
    DEFAULT_RAYCAST_TYPE,
)
from mcp_server.models.physics import (
    CollisionShapeResult,
    PhysicsLayersResult,
    RaycastResult,
    SetupBodyResult,
)
from mcp_server.safety import MUTATING, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

PHYSICS = {PHYSICS_TAG}


def register_physics(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the physics tools."""

    @mcp.tool(meta=MUTATING, tags=PHYSICS)
    @enforce_preconditions
    async def setup_physics_body(
        node_path: str, properties: dict[str, Any], dry_run: bool = False
    ) -> SetupBodyResult:
        """Set physics properties (e.g. mass, gravity_scale) on the body/area at
        ``node_path`` in one call. The node must be a CollisionObject2D/3D.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return SetupBodyResult(node_path=node_path, properties={}, dry_run=True)
        params = {"node_path": node_path, "properties": properties}
        return SetupBodyResult(**await route(bridge, "cmd_setup_physics_body", params))

    @mcp.tool(meta=MUTATING, tags=PHYSICS)
    @enforce_preconditions
    async def setup_collision(
        node_path: str,
        shape_type: str,
        collision_node_type: str = DEFAULT_COLLISION_NODE_TYPE,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> CollisionShapeResult:
        """Add a collision shape under the body/area at ``node_path``: creates a
        ``collision_node_type`` (CollisionShape2D/3D) holding a ``shape_type`` shape
        (e.g. RectangleShape2D) with ``properties`` (size/radius/…).
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return CollisionShapeResult(
                node_path="", shape_type=shape_type, created=False, dry_run=True
            )
        params = {
            "node_path": node_path,
            "shape_type": shape_type,
            "collision_node_type": collision_node_type,
            "properties": properties or {},
        }
        return CollisionShapeResult(**await route(bridge, "cmd_setup_collision", params))

    @mcp.tool(meta=MUTATING, tags=PHYSICS)
    @enforce_preconditions
    async def set_physics_layers(
        node_path: str,
        layers: list[int] | None = None,
        mask: list[int] | None = None,
        dry_run: bool = False,
    ) -> PhysicsLayersResult:
        """Set the collision layer and/or mask on the body/area at ``node_path`` from
        1-based bit indices (e.g. ``layers=[1,3]``). Pass null to leave one unchanged.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return PhysicsLayersResult(node_path=node_path, dry_run=True)
        params = {"node_path": node_path, "layers": layers, "mask": mask}
        return PhysicsLayersResult(**await route(bridge, "cmd_set_physics_layers", params))

    @mcp.tool(meta=MUTATING, tags=PHYSICS)
    @enforce_preconditions
    async def add_raycast(
        parent_path: str,
        name: str = DEFAULT_RAYCAST_NAME,
        raycast_type: str = DEFAULT_RAYCAST_TYPE,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> RaycastResult:
        """Add a raycast node (RayCast2D/3D) named ``name`` under ``parent_path``, with
        ``properties`` such as ``target_position``.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return RaycastResult(node_path="", created=False, dry_run=True)
        params = {
            "parent_path": parent_path,
            "name": name,
            "raycast_type": raycast_type,
            "properties": properties or {},
        }
        return RaycastResult(**await route(bridge, "cmd_add_raycast", params))
