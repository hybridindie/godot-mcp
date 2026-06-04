"""Shader tools (issue #47).

Author shaders over the bridge: create/read ``.gdshader`` files, assign a
ShaderMaterial to a node, and set shader uniform parameters. Gated `shader` toolset.
``read_shader`` is `read_only`; the others are `mutating` (UndoRedo-wrapped addon-side)
with `dry_run`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SHADER_TAG
from mcp_server.defaults import (
    DEFAULT_SHADER_CODE,
)
from mcp_server.models.shader import (
    ShaderMaterialResult,
    ShaderParamResult,
    ShaderReadResult,
    ShaderResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route, run_or_preview

SHADER = {SHADER_TAG}


def register_shader(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the shader tools."""

    @mcp.tool(meta=MUTATING, tags=SHADER)
    @enforce_preconditions
    async def create_shader(
        shader_path: str, code: str = DEFAULT_SHADER_CODE, dry_run: bool = False
    ) -> ShaderResult:
        """Create or overwrite a ``.gdshader`` file at ``shader_path`` (must be
        ``res://``) with ``code`` (defaults to a minimal canvas_item shader). Undoable —
        restores the previous content (or removes the file) on undo.
        """
        params = {"shader_path": shader_path, "code": code}
        preview = {"shader_path": shader_path, "created": False}
        return await run_or_preview(
            dry_run, ShaderResult, preview, bridge, "cmd_create_shader", params
        )

    @mcp.tool(meta=MUTATING, tags=SHADER)
    @enforce_preconditions
    async def assign_shader_material(
        node_path: str, shader_path: str, dry_run: bool = False
    ) -> ShaderMaterialResult:
        """Create a ShaderMaterial wrapping the shader at ``shader_path`` and assign it to
        the node at ``node_path`` (``material`` for CanvasItem, ``material_override`` for
        GeometryInstance3D). Returns which material property was set.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "shader_path": shader_path}
        preview = {
            "node_path": node_path,
            "shader_path": shader_path,
            "material_property": "",
        }
        return await run_or_preview(
            dry_run, ShaderMaterialResult, preview, bridge, "cmd_assign_shader_material", params
        )

    @mcp.tool(meta=MUTATING, tags=SHADER)
    @enforce_preconditions
    async def set_shader_param(
        node_path: str,
        name: str,
        value: Any,
        param_type: str = "",
        dry_run: bool = False,
    ) -> ShaderParamResult:
        """Set the shader uniform ``name`` to ``value`` on the node's ShaderMaterial.
        ``param_type`` coerces ``value``: float / int / bool / vector2 / vector3 /
        vector4 / color (omit to infer — number/bool as-is, ``[x,y,z]`` → vector,
        HTML string → color). The node must have a ShaderMaterial assigned.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "name": name, "value": value, "param_type": param_type}
        preview = {"node_path": node_path, "name": name}
        return await run_or_preview(
            dry_run, ShaderParamResult, preview, bridge, "cmd_set_shader_param", params
        )

    @mcp.tool(meta=READ_ONLY, tags=SHADER)
    async def read_shader(shader_path: str) -> ShaderReadResult:
        """Read the GLSL-like source of the ``.gdshader`` file at ``shader_path``.
        Errors with RESOURCE_NOT_FOUND if the file does not exist.
        """
        params = {"shader_path": shader_path}
        return ShaderReadResult(**await route(bridge, "cmd_read_shader", params))
