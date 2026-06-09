"""Visual shader tools (issue #107).

Create and edit VisualShader node graphs programmatically.  This is the
node-based counterpart to the text-shader `shader` toolset (issue #47).

Gated ``visual_shader`` toolset.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import VISUAL_SHADER_TAG
from mcp_server.models.visual_shader import (
    AddShaderNodeResult,
    ConnectShaderNodesResult,
    CreateVisualShaderResult,
    ListShaderNodeTypesResult,
    SetShaderNodeParamResult,
)
from mcp_server.safety import MUTATING, READ_ONLY
from mcp_server.tools._route import route, run_or_preview

VISUAL_SHADER = {VISUAL_SHADER_TAG}


# ---------------------------------------------------------------------------
# Public tool registration
# ---------------------------------------------------------------------------


def register_visual_shader(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the visual shader tools."""

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def create_visual_shader(
        name: str, type: str = "3d", path: str = "", dry_run: bool = False
    ) -> CreateVisualShaderResult:
        """Create a VisualShader resource with the given ``name`` and ``type``
        (``"2d"`` | ``"3d"`` | ``"particles"`` | ``"sky"`` | ``"fog"``).
        Saves to ``path`` (defaults to ``res://shaders/{name}.tres``).
        """
        params: dict[str, Any] = {"name": name, "type": type, "path": path}
        preview = {
            "path": path or f"res://shaders/{name}.tres",
            "created": False,
        }
        return await run_or_preview(
            dry_run,
            CreateVisualShaderResult,
            preview,
            bridge,
            "cmd_create_visual_shader",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def add_shader_node(
        shader_path: str,
        node_type: str,
        node_id: int,
        position: list[float] | None = None,
        dry_run: bool = False,
    ) -> AddShaderNodeResult:
        """Add a node of ``node_type`` (e.g. ``"VisualShaderNodeColorConstant"``)
        to the VisualShader at ``shader_path``, identified by ``node_id``.
        ``position`` is a ``[x, y]`` list in graph space.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "node_type": node_type,
            "node_id": node_id,
            "position": position or [0.0, 0.0],
        }
        preview = {
            "node_id": node_id,
            "node_type": node_type,
            "added": False,
        }
        return await run_or_preview(
            dry_run,
            AddShaderNodeResult,
            preview,
            bridge,
            "cmd_add_shader_node",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def connect_shader_nodes(
        shader_path: str,
        from_node: int,
        from_port: int,
        to_node: int,
        to_port: int,
        dry_run: bool = False,
    ) -> ConnectShaderNodesResult:
        """Connect output port ``from_port`` on ``from_node`` to input port
        ``to_port`` on ``to_node`` in the VisualShader at ``shader_path``.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "from_node": from_node,
            "from_port": from_port,
            "to_node": to_node,
            "to_port": to_port,
        }
        preview = {"connected": False}
        return await run_or_preview(
            dry_run,
            ConnectShaderNodesResult,
            preview,
            bridge,
            "cmd_connect_shader_nodes",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def set_shader_node_param(
        shader_path: str,
        node_id: int,
        property: str,
        value: Any,
        dry_run: bool = False,
    ) -> SetShaderNodeParamResult:
        """Set ``property`` on the node identified by ``node_id`` in the
        VisualShader at ``shader_path``.  Values are coerced by the addon to
        the property's declared Godot type.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "node_id": node_id,
            "property": property,
            "value": value,
        }
        preview = {
            "node_id": node_id,
            "property": property,
            "value": value,
            "set": False,
        }
        return await run_or_preview(
            dry_run,
            SetShaderNodeParamResult,
            preview,
            bridge,
            "cmd_set_shader_node_param",
            params,
        )

    @mcp.tool(meta=READ_ONLY, tags=VISUAL_SHADER)
    async def list_shader_node_types() -> ListShaderNodeTypesResult:
        """Return the built-in VisualShader node types available in the
        connected Godot editor (from a ClassDB scan).
        """
        return ListShaderNodeTypesResult(
            **await route(bridge, "cmd_list_shader_node_types")
        )
