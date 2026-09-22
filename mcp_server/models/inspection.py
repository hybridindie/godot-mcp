"""Typed models for read-only inspection tools (issue #5).

Mirror the JSON-safe shapes the addon returns. ``snake_case`` throughout.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_serializer


class ProjectInfo(BaseModel):
    """Project-level context."""

    name: str
    godot_version: str
    main_scene: str | None = None
    project_path: str | None = None
    autoloads: dict[str, str] = Field(default_factory=dict)
    input_actions: list[str] = Field(default_factory=list)


class ActiveScene(BaseModel):
    """The currently open scene, or ``is_open=False`` when none is open."""

    is_open: bool
    path: str | None = None
    name: str | None = None


class SceneEntry(BaseModel):
    """One project scene file and its editor state (#304)."""

    path: str
    is_main: bool = False  # the project's configured main scene
    is_open: bool = False  # currently open in an editor tab
    is_active: bool = False  # the currently edited (foreground) scene


class ScenesResult(BaseModel):
    """The project's scene files + which is main, for open-vs-create decisions (#304).

    ``scenes`` is empty for a project with no scenes yet (a net-new signal, not an error).
    """

    scenes: list[SceneEntry] = Field(default_factory=list)
    main_scene: str | None = None


class SceneNode(BaseModel):
    """A node in the recursive scene-tree serialization.

    ``path`` is the scene-relative path (``"."`` for the root, e.g. ``Player/Weapon``
    below it), accepted verbatim by the path-taking tools (#180) — clients never have
    to reconstruct paths by walking the tree.

    #487: instanced nodes (they come from another scene) carry ``owner`` — the
    source scene's ``res://`` path — so agents can tell them apart from local
    nodes; ``editable_children: true`` rides the instance whose Editable Children
    is on. Local nodes carry neither field (the default surface stays small).
    """

    name: str
    type: str
    path: str = ""
    script: str | None = None
    owner: str | None = None
    editable_children: bool | None = None
    children: list[SceneNode] = Field(default_factory=list)

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        """Omit ``owner``/``editable_children`` when unset — local nodes carry
        neither key on the wire (FastMCP builds structured_content via
        pydantic-core, which only honors this hook)."""
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "script": self.script,
        }
        if self.owner is not None:
            data["owner"] = self.owner
        if self.editable_children is not None:
            data["editable_children"] = self.editable_children
        data["children"] = self.children
        return data


class SceneTree(BaseModel):
    """The active scene tree, or ``tree=None`` when no scene is open."""

    tree: SceneNode | None = None
    # Output bounding (issue #222): set when the full tree exceeded the character
    # limit and a lightweight view was returned instead; ``hint`` says how to narrow.
    truncated: bool = False
    hint: str | None = None


class NodeInfo(BaseModel):
    """Full detail for a single node (path, type, script, properties, children)."""

    node_path: str
    type: str
    script: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)


class NodePropertyList(BaseModel):
    """All property names for a node, returned by get_node_property_list."""

    node_path: str
    type: str = ""
    properties: list[str] = Field(default_factory=list)


class NodeProperty(BaseModel):
    """A single node property read (issue #215), including built-in Godot properties.

    ``value`` is JSON-coerced (see type_coerce.gd); ``exists`` is false (and ``value``
    null) when the node has no such property.
    """

    node_path: str
    property: str
    value: Any = None
    exists: bool = False


class NodeGroups(BaseModel):
    """A node's group memberships (issue #216), editor-internal groups excluded.

    Inverts ``add_to_group`` / ``remove_from_group`` and lets ``delete_node`` restore
    membership.
    """

    node_path: str
    groups: list[str] = Field(default_factory=list)


class SelectedNode(BaseModel):
    """The selected node, or ``selected=None`` when nothing is selected."""

    selected: NodeInfo | None = None


class SnapshotResult(BaseModel):
    """A subtree snapshot (issue #535): a stable id + the serialized subtree.

    ``snapshot_id`` references the server-side bounded store — pass it to
    ``diff_snapshots`` (as ``before_id``/``after_id``) instead of re-serializing.
    """

    snapshot_id: str
    node_path: str
    snapshot: dict[str, Any] = Field(default_factory=dict)


class DiffEntry(BaseModel):
    """One property-level difference between two snapshots (issue #535)."""

    node: str
    property: str
    before: Any = None
    after: Any = None


class SnapshotDiff(BaseModel):
    """The diff of two subtree snapshots (issue #535).

    ``added``/``removed`` list node paths; ``changed`` lists per-property
    before/after pairs (JSON-coerced shapes). All three empty = identical.
    """

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[DiffEntry] = Field(default_factory=list)
