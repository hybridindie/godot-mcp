"""Typed results for batch / refactor tools (issue #48)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.persistence import TargetPersistence


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
    # #461: false when the batch exceeded the 20-node UndoRedo threshold and was
    # applied directly — undo will not revert it. True when every applied set is
    # undo-tracked (or nothing was applied).
    undoable: bool = True
    hint: str | None = None
    # #477: one verdict per applied target (node_path/persisted/reason/hint).
    # `_batch_targets` descends into instanced children, so a target inside a
    # non-editable instance is individually lost on save even when the batch
    # reports ok.
    persistence: list[TargetPersistence] = Field(default_factory=list)


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
