"""Typed results for visual shader tools (issue #107)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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
