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
    ShaderParamReadResult,
    ShaderParamResult,
    ShaderReadResult,
    ShaderResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route, run_or_preview

SHADER = {SHADER_TAG}

# The slots a node's ShaderMaterial can sit in (CanvasItem, GeometryInstance3D).
MATERIAL_PROPERTIES = ["material", "material_override"]


def assign_material_probe(node_path: str) -> dict[str, Any]:
    """``cmd_node_persistence`` params for an ``assign_shader_material`` preview: the new
    material has no file yet, so it saves (or not) with its node."""
    return {"node_path": node_path}


def set_param_probe(node_path: str) -> dict[str, Any]:
    """``cmd_node_persistence`` params for a ``set_shader_param`` preview: a uniform edit
    saves wherever the node's current material lives (#475)."""
    return {"node_path": node_path, "resource_properties": MATERIAL_PROPERTIES}


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
        GeometryInstance3D). Returns which material property was set, and ``persisted``:
        ``False`` (with a ``reason`` token and ``hint``) when the material applies live but
        will not be saved — e.g. the node is inside an instanced scene without Editable
        Children. A ``dry_run`` preview asks the addon for the same verdict without assigning.
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "shader_path": shader_path}
        if dry_run:
            # #458 round-2: the preview must be honest about persistence — probe
            # the addon read-only instead of hardcoding persisted:true.
            truth = await route(bridge, "cmd_node_persistence", assign_material_probe(node_path))
            return ShaderMaterialResult(
                node_path=node_path,
                shader_path=shader_path,
                material_property="",
                assigned=False,
                persisted=truth.get("persisted", True),
                reason=truth.get("reason"),
                hint=truth.get("hint"),
                dry_run=True,
            )
        return ShaderMaterialResult(**await route(bridge, "cmd_assign_shader_material", params))

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
        ``value`` accepts JSON for the target Godot type — Vector2/3 as
        ``{"x":1,"y":2}``/``[1,2]``, Color as ``{"r":1,"g":0,"b":0,"a":1}`` or
        ``"#ff0000"``, Rect2 as ``{"position":{...},"size":{...}}``, NodePath/StringName
        as a string, primitives as-is. See docs/tool-contracts.md#value-shapes.
        Reports ``persisted`` like ``assign_shader_material``: ``False`` when the edit will
        not be saved — the node is inside an instance without Editable Children, or the
        material is embedded in another scene/resource file (``reason`` says which).
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "name": name, "value": value, "param_type": param_type}
        if dry_run:
            # #458 round-2: the preview carries the same persistence truth as the
            # real run (read-only probe), so an instanced-child preview isn't
            # dishonest about saving.
            truth = await route(bridge, "cmd_node_persistence", set_param_probe(node_path))
            return ShaderParamResult(
                node_path=node_path,
                name=name,
                set=False,
                persisted=truth.get("persisted", True),
                reason=truth.get("reason"),
                hint=truth.get("hint"),
                dry_run=True,
            )
        return ShaderParamResult(**await route(bridge, "cmd_set_shader_param", params))

    @mcp.tool(meta=READ_ONLY, tags=SHADER)
    async def get_shader_param(node_path: str, name: str) -> ShaderParamReadResult:
        """Read the live value of shader uniform ``name`` on the node's
        ShaderMaterial — the read-only inverse of ``set_shader_param``. Returns
        ``exists=False`` when the material's shader does not declare the uniform.
        ``value`` is null when the uniform has never been set on this material (the
        shader's own default applies).
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "name": name}
        return ShaderParamReadResult(**await route(bridge, "cmd_get_shader_param", params))

    @mcp.tool(meta=READ_ONLY, tags=SHADER)
    async def read_shader(shader_path: str) -> ShaderReadResult:
        """Read the GLSL-like source of the ``.gdshader`` file at ``shader_path``.
        Errors with RESOURCE_NOT_FOUND if the file does not exist.
        """
        params = {"shader_path": shader_path}
        return ShaderReadResult(**await route(bridge, "cmd_read_shader", params))
