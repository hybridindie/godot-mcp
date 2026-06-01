"""Typed results for node-parity tools (issue #31)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DuplicateNodeResult(BaseModel):
    node_path: str  # the new node's scene-relative path ("" on dry_run)
    source_path: str
    dry_run: bool = False


class MoveNodeResult(BaseModel):
    node_path: str
    moved: bool
    dry_run: bool = False


class GroupResult(BaseModel):
    node_path: str
    group: str
    in_group: bool  # membership after the call
    changed: bool = False  # whether this call actually changed membership
    dry_run: bool = False


class SignalConnection(BaseModel):
    signal: str
    target_path: str
    method: str
    persistent: bool = False


class SignalConnectionList(BaseModel):
    node_path: str
    connections: list[SignalConnection] = Field(default_factory=list)


class DisconnectSignalResult(BaseModel):
    source_path: str
    signal_name: str
    target_path: str
    method_name: str
    disconnected: bool
    dry_run: bool = False
