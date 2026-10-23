"""Result models for composite/macro tools (issue #154).

Composite tools collapse a multi-step workflow into one bridge round-trip that
the addon runs as a single UndoRedo action. ``snake_case`` fields, typed models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.persistence import TargetPersistence
from mcp_server.models.receipt import ChangeReceipt


class ChildSpec(BaseModel):
    """One child for ``compose_node`` (issue #691: a typed shape so the schema
    guides client generation instead of a bare ``object``)."""

    node_type: str
    node_name: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class NodeEdit(BaseModel):
    """One ``{node_path, properties}`` entry for ``apply_node_edits`` (issue #691)."""

    node_path: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ComposeNodeResult(BaseModel):
    """Outcome of ``compose_node`` (create a node with properties/script/children)."""

    node_path: str
    created: bool
    children: list[str] = Field(default_factory=list)
    script_attached: bool = False
    properties_set: list[str] = Field(default_factory=list)
    saved: bool = False
    dry_run: bool = False
    receipt: ChangeReceipt | None = None


class BatchCreateNodesResult(BaseModel):
    """Outcome of ``batch_create_nodes`` (many same-typed nodes under one parent)."""

    created: list[str] = Field(default_factory=list)
    count: int = 0
    saved: bool = False
    dry_run: bool = False
    # #523: the shared UndoRedo threshold — above it the create bypasses the
    # undo stack for perf and `hint` explains what that means (honest batch).
    undoable: bool = True
    hint: str = ""
    receipt: ChangeReceipt | None = None


class ApplyNodeEditsResult(BaseModel):
    """Outcome of ``apply_node_edits`` (per-node property edits in one action)."""

    edited: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    saved: bool = False
    # #523: the shared UndoRedo threshold honesty shape (same as batch_set_property).
    undoable: bool = True
    hint: str = ""
    dry_run: bool = False
    # #477: per-entry verdict for every edited node — an entry inside a
    # non-editable instance applies live but is lost on save.
    persistence: list[TargetPersistence] = Field(default_factory=list)
    receipt: ChangeReceipt | None = None
