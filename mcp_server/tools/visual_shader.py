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
    AddShaderGroupNodeResult,
    AddShaderNodeResult,
    ConnectShaderNodesResult,
    CreateShaderGroupResult,
    CreateVisualShaderResult,
    ListShaderNodeTypesResult,
    RemoveShaderGroupNodeResult,
    RemoveShaderGroupResult,
    RenameShaderGroupResult,
    SetShaderNodeParamResult,
    VisualShaderGraph,
)
from mcp_server.paths import ResPath
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    enforce_preconditions,
    require_confirmation,
)
from mcp_server.tools._route import route, run_or_preview

VISUAL_SHADER = {VISUAL_SHADER_TAG}


# ---------------------------------------------------------------------------
# Public tool registration
# ---------------------------------------------------------------------------


def register_visual_shader(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the visual shader tools."""

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def create_visual_shader(
        name: str, type: str = "3d", path: ResPath = "", dry_run: bool = False
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
        shader_path: ResPath,
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
        shader_path: ResPath,
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
        shader_path: ResPath,
        node_id: int,
        property: str,
        value: Any,
        dry_run: bool = False,
    ) -> SetShaderNodeParamResult:
        """Set ``property`` on the node identified by ``node_id`` in the
        VisualShader at ``shader_path``.  Values are coerced by the addon to
        the property's declared Godot type.
        ``value`` accepts JSON for the target Godot type — Vector2/3 as
        ``{"x":1,"y":2}``/``[1,2]``, Color as ``{"r":1,"g":0,"b":0,"a":1}`` or
        ``"#ff0000"``, Rect2 as ``{"position":{...},"size":{...}}``, NodePath/StringName
        as a string, primitives as-is. See docs/tool-contracts.md#value-shapes.
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

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def create_shader_group(
        shader_path: ResPath,
        name: str,
        node_id: int,
        position: list[float] | None = None,
        dry_run: bool = False,
    ) -> CreateShaderGroupResult:
        """Create a node group named ``name`` at ``node_id`` (>=2) in the shader
        at ``shader_path``. Add members with ``add_group_node``. Godot 4.8+.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "name": name,
            "node_id": node_id,
            "position": position or [0.0, 0.0],
        }
        preview = {"node_id": node_id, "name": name, "created": False}
        return await run_or_preview(
            dry_run,
            CreateShaderGroupResult,
            preview,
            bridge,
            "cmd_create_shader_group",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def rename_shader_group(
        shader_path: ResPath,
        node_id: int,
        name: str,
        dry_run: bool = False,
    ) -> RenameShaderGroupResult:
        """Rename the group at group-node ``node_id`` in the shader at
        ``shader_path``. Godot 4.8+.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "node_id": node_id,
            "name": name,
        }
        preview = {"node_id": node_id, "name": name, "renamed": False}
        return await run_or_preview(
            dry_run,
            RenameShaderGroupResult,
            preview,
            bridge,
            "cmd_rename_shader_group",
            params,
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=VISUAL_SHADER)
    @enforce_preconditions
    async def remove_shader_group(
        shader_path: ResPath,
        node_id: int,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> RemoveShaderGroupResult:
        """Remove the group at ``node_id`` and its subgraph; undo restores both.
        Destructive (``confirm=True``). Godot 4.8+.
        """
        if not dry_run:
            require_confirmation(confirm, "remove_shader_group")
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "node_id": node_id,
        }
        preview = {"node_id": node_id, "name": "", "removed": False}
        return await run_or_preview(
            dry_run,
            RemoveShaderGroupResult,
            preview,
            bridge,
            "cmd_remove_shader_group",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=VISUAL_SHADER)
    async def add_shader_group_node(
        shader_path: ResPath,
        group_node_id: int,
        node_type: str,
        node_id: int,
        position: list[float] | None = None,
        dry_run: bool = False,
    ) -> AddShaderGroupNodeResult:
        """Add a ``node_type`` at group-local ``node_id`` to the group at
        ``group_node_id``; ``position`` is [x,y], group ids start at 0. Godot 4.8+.
        """
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "group_node_id": group_node_id,
            "node_type": node_type,
            "node_id": node_id,
            "position": position or [0.0, 0.0],
        }
        preview = {
            "group_node_id": group_node_id,
            "node_id": node_id,
            "node_type": node_type,
            "added": False,
        }
        return await run_or_preview(
            dry_run,
            AddShaderGroupNodeResult,
            preview,
            bridge,
            "cmd_add_shader_group_node",
            params,
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=VISUAL_SHADER)
    @enforce_preconditions
    async def remove_shader_group_node(
        shader_path: ResPath,
        group_node_id: int,
        node_id: int,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> RemoveShaderGroupNodeResult:
        """Remove node ``node_id`` from the group at ``group_node_id``; undo
        restores it and its connections. Destructive (``confirm=True``). Godot 4.8+.
        """
        if not dry_run:
            require_confirmation(confirm, "remove_shader_group_node")
        params: dict[str, Any] = {
            "shader_path": shader_path,
            "group_node_id": group_node_id,
            "node_id": node_id,
        }
        preview = {"group_node_id": group_node_id, "node_id": node_id, "removed": False}
        return await run_or_preview(
            dry_run,
            RemoveShaderGroupNodeResult,
            preview,
            bridge,
            "cmd_remove_shader_group_node",
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

    @mcp.tool(meta=READ_ONLY, tags=VISUAL_SHADER)
    async def read_visual_shader(shader_path: ResPath) -> VisualShaderGraph:
        """Read the VisualShader at ``shader_path``: ``mode``, every ``node``
        ({id, type, position, parameters}), ``connection``, and ``groups``
        ({node_id, name, members}; empty before 4.8). Snapshot before editing
        for rollback. Errors if the path isn't a VisualShader resource.
        """
        return VisualShaderGraph(
            **await route(bridge, "cmd_read_visual_shader", {"shader_path": shader_path})
        )
