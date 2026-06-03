"""Typed results for scene mutation tools (issue #6).

Each result echoes ``dry_run`` so the agent can tell a preview from a real change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CreateNodeResult(BaseModel):
    node_path: str
    created: bool
    dry_run: bool = False


class RenameNodeResult(BaseModel):
    node_path: str
    new_name: str
    renamed: bool
    old_name: str | None = None
    dry_run: bool = False


class SetPropertyResult(BaseModel):
    node_path: str
    property: str
    value: Any = None
    set: bool = False
    dry_run: bool = False


class DeleteNodeResult(BaseModel):
    node_path: str
    deleted: bool
    dry_run: bool = False


class AttachScriptResult(BaseModel):
    node_path: str
    script_path: str
    attached: bool
    dry_run: bool = False


class ConnectSignalResult(BaseModel):
    source_path: str
    signal_name: str
    target_path: str
    method_name: str
    connected: bool
    dry_run: bool = False


class SaveSceneResult(BaseModel):
    saved: bool
    path: str | None = None
    dry_run: bool = False


class CreateSceneResult(BaseModel):
    scene_path: str
    root_type: str
    created: bool
    dry_run: bool = False


class InstanceSceneResult(BaseModel):
    node_path: str
    scene_path: str
    instanced: bool
    dry_run: bool = False
