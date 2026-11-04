"""Typed results for visual shader tools (issue #107)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateVisualShaderResult(BaseModel):
    path: str
    created: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class AddShaderNodeResult(BaseModel):
    node_id: int
    node_type: str
    added: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class ConnectShaderNodesResult(BaseModel):
    connected: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class SetShaderNodeParamResult(BaseModel):
    node_id: int
    property: str
    value: Any = None
    set: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class ListShaderNodeTypesResult(BaseModel):
    types: list[str]


class CreateShaderGroupResult(BaseModel):
    node_id: int
    name: str
    created: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class RenameShaderGroupResult(BaseModel):
    node_id: int
    name: str
    renamed: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class RemoveShaderGroupResult(BaseModel):
    node_id: int
    name: str = ""
    removed: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class AddShaderGroupNodeResult(BaseModel):
    group_node_id: int
    node_id: int
    node_type: str
    added: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class RemoveShaderGroupNodeResult(BaseModel):
    group_node_id: int
    node_id: int
    removed: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class VisualShaderNodeInfo(BaseModel):
    """One node in a VisualShader graph (issue #219 G6): its ``id``, ``type`` (the
    VisualShaderNode class), editor ``position``, and serialized ``parameters`` — enough
    to recreate it via ``add_shader_node`` + ``set_shader_node_param``. ``group`` is
    the owning group's node id for nodes inside a group (``None`` for top-level
    nodes; issue #601)."""

    id: int
    type: str
    position: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    group: int | None = None


class VisualShaderGroupInfo(BaseModel):
    """One VisualShader node group/subgraph (issue #601, Godot 4.8+): the group
    node's ``node_id`` in the parent shader, its ``name``, and its member node
    list. Empty on 4.4–4.7 (groups don't exist there)."""

    node_id: int
    name: str
    members: list[VisualShaderNodeInfo] = Field(default_factory=list)


class VisualShaderConnection(BaseModel):
    """One edge in a VisualShader graph (issue #219 G6) — the inverse of
    ``connect_shader_nodes``."""

    from_node: int
    from_port: int
    to_node: int
    to_port: int


class VisualShaderGraph(BaseModel):
    """A serialized VisualShader graph (issue #219 G6) — the inverse of
    ``create_visual_shader`` / ``add_shader_node`` / ``connect_shader_nodes`` /
    ``set_shader_node_param``. ``mode`` is the shader mode (spatial / canvas_item /
    particles / sky / fog). ``groups`` reports node groups and their members
    (issue #601; empty before Godot 4.8)."""

    shader_path: str
    mode: str
    nodes: list[VisualShaderNodeInfo] = Field(default_factory=list)
    connections: list[VisualShaderConnection] = Field(default_factory=list)
    groups: list[VisualShaderGroupInfo] = Field(default_factory=list)
