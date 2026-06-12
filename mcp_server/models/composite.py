"""Result models for composite/macro tools (issue #154).

Composite tools collapse a multi-step workflow into one bridge round-trip that
the addon runs as a single UndoRedo action. ``snake_case`` fields, typed models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComposeNodeResult(BaseModel):
    """Outcome of ``compose_node`` (create a node with properties/script/children)."""

    node_path: str
    created: bool
    children: list[str] = Field(default_factory=list)
    script_attached: bool = False
    properties_set: list[str] = Field(default_factory=list)
    saved: bool = False
    dry_run: bool = False


class BatchCreateNodesResult(BaseModel):
    """Outcome of ``batch_create_nodes`` (many same-typed nodes under one parent)."""

    created: list[str] = Field(default_factory=list)
    count: int = 0
    saved: bool = False
    dry_run: bool = False


class ApplyNodeEditsResult(BaseModel):
    """Outcome of ``apply_node_edits`` (per-node property edits in one action)."""

    edited: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    saved: bool = False
    dry_run: bool = False
