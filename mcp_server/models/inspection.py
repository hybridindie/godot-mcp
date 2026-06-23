"""Typed models for read-only inspection tools (issue #5).

Mirror the JSON-safe shapes the addon returns. ``snake_case`` throughout.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class SceneNode(BaseModel):
    """A node in the recursive scene-tree serialization.

    ``path`` is the scene-relative path (``"."`` for the root, e.g. ``Player/Weapon``
    below it), accepted verbatim by the path-taking tools (#180) — clients never have
    to reconstruct paths by walking the tree.
    """

    name: str
    type: str
    path: str = ""
    script: str | None = None
    children: list[SceneNode] = Field(default_factory=list)


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


class SelectedNode(BaseModel):
    """The selected node, or ``selected=None`` when nothing is selected."""

    selected: NodeInfo | None = None
