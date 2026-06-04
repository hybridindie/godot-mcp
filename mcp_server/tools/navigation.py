"""Navigation tools (issue #43).

Author navigation over the bridge: navigation regions (with a navmesh/navpoly
resource), navigation agents, navmesh baking, and navigation-layer bitmasks. Gated
`navigation` toolset; all `mutating` (UndoRedo-wrapped addon-side) with `dry_run`.
Generic over 2D/3D — pass the node type names (``NavigationRegion2D`` /
``NavigationRegion3D``, ``NavigationAgent2D`` / ``NavigationAgent3D``).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import NAVIGATION_TAG
from mcp_server.defaults import (
    DEFAULT_NAV_AGENT_TYPE,
    DEFAULT_NAV_REGION_TYPE,
)
from mcp_server.models.navigation import (
    BakeNavigationResult,
    NavigationAgentResult,
    NavigationLayersResult,
    NavigationRegionResult,
)
from mcp_server.safety import MUTATING, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

NAVIGATION = {NAVIGATION_TAG}


def register_navigation(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the navigation tools."""

    @mcp.tool(meta=MUTATING, tags=NAVIGATION)
    @enforce_preconditions
    async def setup_navigation_region(
        parent_path: str,
        region_type: str = DEFAULT_NAV_REGION_TYPE,
        name: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> NavigationRegionResult:
        """Add a NavigationRegion2D/3D under ``parent_path`` with an empty navmesh
        resource assigned (NavigationPolygon for 2D, NavigationMesh for 3D), ready to
        bake. ``properties`` (e.g. ``enabled``, ``navigation_layers``) are applied.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return NavigationRegionResult(
                node_path="", region_type=region_type, created=False, dry_run=True
            )
        params = {
            "parent_path": parent_path,
            "region_type": region_type,
            "name": name or region_type,
            "properties": properties or {},
        }
        return NavigationRegionResult(**await route(bridge, "cmd_setup_navigation_region", params))

    @mcp.tool(meta=MUTATING, tags=NAVIGATION)
    @enforce_preconditions
    async def setup_navigation_agent(
        parent_path: str,
        agent_type: str = DEFAULT_NAV_AGENT_TYPE,
        name: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> NavigationAgentResult:
        """Add a NavigationAgent2D/3D under ``parent_path`` configured with
        ``properties`` such as ``radius``, ``path_desired_distance``,
        ``target_desired_distance``, ``max_speed``, ``avoidance_enabled``.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return NavigationAgentResult(
                node_path="", agent_type=agent_type, created=False, dry_run=True
            )
        params = {
            "parent_path": parent_path,
            "agent_type": agent_type,
            "name": name or agent_type,
            "properties": properties or {},
        }
        return NavigationAgentResult(**await route(bridge, "cmd_setup_navigation_agent", params))

    @mcp.tool(meta=MUTATING, tags=NAVIGATION)
    @enforce_preconditions
    async def bake_navigation_mesh(node_path: str, dry_run: bool = False) -> BakeNavigationResult:
        """Bake the navigation mesh/polygon for the NavigationRegion2D/3D at
        ``node_path`` from the scene geometry (synchronous). The region must have a
        navmesh resource assigned (``setup_navigation_region`` creates one).
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return BakeNavigationResult(node_path=node_path, baked=False, dry_run=True)
        params = {"node_path": node_path}
        return BakeNavigationResult(**await route(bridge, "cmd_bake_navigation_mesh", params))

    @mcp.tool(meta=MUTATING, tags=NAVIGATION)
    @enforce_preconditions
    async def set_navigation_layers(
        node_path: str, layers: list[int], dry_run: bool = False
    ) -> NavigationLayersResult:
        """Set the navigation-layer bitmask on the region/agent at ``node_path`` from
        1-based bit indices (e.g. ``layers=[1,3]`` → bitmask 5). Works on any node with
        a ``navigation_layers`` property.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return NavigationLayersResult(node_path=node_path, dry_run=True)
        params = {"node_path": node_path, "layers": layers}
        return NavigationLayersResult(**await route(bridge, "cmd_set_navigation_layers", params))
