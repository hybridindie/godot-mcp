"""Typed results for visual shader tools (issue #107)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateVisualShaderResult(BaseModel):
    path: str
    created: bool = False
    dry_run: bool = False


class AddShaderNodeResult(BaseModel):
    node_id: int
    node_type: str
    added: bool = False
    dry_run: bool = False


class ConnectShaderNodesResult(BaseModel):
    connected: bool = False
    dry_run: bool = False


class SetShaderNodeParamResult(BaseModel):
    node_id: int
    property: str
    value: Any = None
    set: bool = False
    dry_run: bool = False


class ListShaderNodeTypesResult(BaseModel):
    types: list[str]


class VisualShaderNodeInfo(BaseModel):
    """One node in a VisualShader graph (issue #219 G6): its ``id``, ``type`` (the
    VisualShaderNode class), editor ``position``, and serialized ``parameters`` — enough
    to recreate it via ``add_shader_node`` + ``set_shader_node_param``."""

    id: int
    type: str
    position: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


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
    particles / sky / fog)."""

    shader_path: str
    mode: str
    nodes: list[VisualShaderNodeInfo] = Field(default_factory=list)
    connections: list[VisualShaderConnection] = Field(default_factory=list)
