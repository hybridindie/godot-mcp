"""Typed results for scene mutation tools (issue #6).

Each result echoes ``dry_run`` so the agent can tell a preview from a real change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mcp_server.models.json_strict import JSONBool, JSONInt, JSONStr
from mcp_server.models.persistence import PersistenceReport


class CreateNodeResult(PersistenceReport):
    node_path: JSONStr
    created: JSONBool
    dry_run: JSONBool = False


class RenameNodeResult(PersistenceReport):
    node_path: JSONStr
    new_name: JSONStr
    renamed: JSONBool
    old_name: JSONStr | None = None
    dry_run: JSONBool = False


class SetPropertyResult(PersistenceReport):
    node_path: JSONStr
    property: JSONStr
    value: Any = None
    set: JSONBool = False
    dry_run: JSONBool = False


class DeleteNodeResult(PersistenceReport):
    node_path: JSONStr
    deleted: JSONBool
    dry_run: JSONBool = False


class AttachScriptResult(PersistenceReport):
    node_path: JSONStr
    script_path: JSONStr
    attached: JSONBool
    dry_run: JSONBool = False


class ConnectSignalResult(BaseModel):
    source_path: JSONStr
    signal_name: JSONStr
    target_path: JSONStr
    method_name: JSONStr
    connected: JSONBool
    # True when the connection already existed (e.g. saved in the scene file);
    # the addon treats that as an idempotent success rather than a failure (#152).
    already_connected: JSONBool = False
    dry_run: JSONBool = False


class SaveSceneResult(BaseModel):
    saved: JSONBool
    path: JSONStr | None = None
    dry_run: JSONBool = False


class CreateSceneResult(BaseModel):
    scene_path: JSONStr
    root_type: JSONStr
    created: JSONBool
    dry_run: JSONBool = False


class InstanceSceneResult(PersistenceReport):
    node_path: JSONStr
    scene_path: JSONStr
    instanced: JSONBool
    dry_run: JSONBool = False


class ExtractSceneResult(PersistenceReport):
    """Result of extracting a subtree into a reusable .tscn (issue #531).

    ``node_count`` sizes the extracted subtree (the dry-run preview's node list
    count). ``instance_path`` is the scene-relative path of the replacement
    instance when ``replace_with_instance`` was requested (empty otherwise).
    """

    node_path: JSONStr
    scene_path: JSONStr
    extracted: JSONBool
    replaced: JSONBool = False
    saved: JSONBool = False
    node_count: JSONInt = 0
    instance_path: JSONStr | None = None
    dry_run: JSONBool = False


class SetEditableChildrenResult(PersistenceReport):
    node_path: JSONStr
    editable: JSONBool
    dry_run: JSONBool = False
