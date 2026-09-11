"""Typed results for shader tools (issue #47)."""

from __future__ import annotations

from typing import Any

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
    # #458: persistence truth — an instanced child renders live but never saves.
    assigned: bool = False
    persisted: bool = True
    reason: str | None = None
    hint: str | None = None
    dry_run: bool = False


class ShaderParamResult(BaseModel):
    node_path: str
    name: str
    # #460: the landed value (read-back after commit), not the requested one.
    value: Any = None
    set: bool = False
    persisted: bool = True
    reason: str | None = None
    hint: str | None = None
    dry_run: bool = False


class ShaderParamReadResult(BaseModel):
    node_path: str
    name: str
    value: Any = None
    exists: bool = False
