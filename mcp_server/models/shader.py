"""Typed results for shader tools (issue #47)."""

from __future__ import annotations

from pydantic import BaseModel


class ShaderResult(BaseModel):
    shader_path: str
    created: bool = False
    dry_run: bool = False


class ShaderReadResult(BaseModel):
    shader_path: str
    code: str


class ShaderMaterialResult(BaseModel):
    node_path: str
    shader_path: str
    material_property: str
    dry_run: bool = False


class ShaderParamResult(BaseModel):
    node_path: str
    name: str
    dry_run: bool = False
