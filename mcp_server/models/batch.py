"""Typed results for batch / refactor tools (issue #48)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeRef(BaseModel):
    path: str
    name: str
    type: str


class FindNodesResult(BaseModel):
    type: str
    nodes: list[NodeRef] = Field(default_factory=list)
    count: int = 0
    # Pagination (issue #222): ``nodes`` is a page of ``total`` matches.
    total: int = 0
    returned: int = 0
    truncated: bool = False
    next_offset: int | None = None


class BatchSetResult(BaseModel):
    property: str
    applied: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    dry_run: bool = False


class CrossSceneSceneResult(BaseModel):
    scene: str
    modified: int = 0
    error: str = ""


class CrossSceneResult(BaseModel):
    results: list[CrossSceneSceneResult] = Field(default_factory=list)
    total_modified: int = 0
    scenes: int = 0
    dry_run: bool = False


class Dependency(BaseModel):
    raw: str
    path: str = ""
    type: str = ""


class DependenciesResult(BaseModel):
    path: str
    dependencies: list[Dependency] = Field(default_factory=list)
    count: int = 0
