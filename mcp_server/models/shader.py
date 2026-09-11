"""Typed results for shader tools (issue #47)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mcp_server.models.persistence import PersistenceReport


class ShaderResult(BaseModel):
    shader_path: str
    created: bool = False
    dry_run: bool = False


class ShaderReadResult(BaseModel):
    shader_path: str
    code: str


class ShaderMaterialResult(PersistenceReport):
    node_path: str
    shader_path: str
    material_property: str
    dry_run: bool = False


class ShaderParamResult(PersistenceReport):
    node_path: str
    name: str
    dry_run: bool = False


class ShaderParamReadResult(BaseModel):
    node_path: str
    name: str
    value: Any = None
    exists: bool = False
