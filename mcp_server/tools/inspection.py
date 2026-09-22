"""Read-only inspection tools (issue #5).

The most frequently called tools: they let an agent understand the project and
scene before making changes. All ``read_only`` — they never mutate anything.
Each is a thin wrapper that routes to the addon and returns a typed model.
"""

from __future__ import annotations

from typing import Any, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import INSPECTION_TAG
from mcp_server.constraints import MaxDepth
from mcp_server.models.inspection import (
    ActiveScene,
    DiffEntry,
    NodeGroups,
    NodeInfo,
    NodeProperty,
    NodePropertyList,
    ProjectInfo,
    ScenesResult,
    SceneTree,
    SelectedNode,
    SnapshotDiff,
    SnapshotResult,
)
from mcp_server.output import TRUNCATION_HINT, over_character_limit
from mcp_server.safety import READ_ONLY
from mcp_server.snapshots import SnapshotStore
from mcp_server.tools._route import route

INSPECTION = {INSPECTION_TAG}


class TreeDiff(TypedDict):
    """The diff_trees result: added/removed node paths + property-level changes."""

    added: list[str]
    removed: list[str]
    changed: list[dict[str, Any]]


def diff_trees(before: dict[str, Any], after: dict[str, Any]) -> TreeDiff:
    """Diff two serialized subtrees (issue #535): added/removed node paths and
    per-property changed entries. Pure function over the JSON-safe snapshot dicts.

    Nodes are keyed by their scene-relative ``path``; a node present on both
    sides is compared property-by-property (script vars + any snapshot-captured
    properties), each difference emitted as ``{node, property, before, after}``.
    """
    added: list[str] = []
    removed: list[str] = []
    changed: list[dict[str, Any]] = []
    before_nodes = _flatten_nodes(before)
    after_nodes = _flatten_nodes(after)
    for path, before_node in before_nodes.items():
        after_node = after_nodes.get(path)
        if after_node is None:
            removed.append(path)
            continue
        before_props = before_node.get("properties") or {}
        after_props = after_node.get("properties") or {}
        for prop in before_props:
            if prop in after_props and after_props[prop] != before_props[prop]:
                changed.append(
                    {
                        "node": path,
                        "property": prop,
                        "before": before_props[prop],
                        "after": after_props[prop],
                    }
                )
    for path in after_nodes:
        if path not in before_nodes:
            added.append(path)
    return {"added": added, "removed": removed, "changed": changed}


def _flatten_nodes(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten a serialized tree to {path: node}, children before parents skipped —
    every node carries its own explicit ``path`` (#180), so no re-derivation."""
    out: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        path = node.get("path", "")
        if path:
            out[path] = node
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    return out


def register_inspection(mcp: FastMCP, bridge: Bridge) -> None:
    """Register all inspection tools on the server."""
    # Server-owned snapshot store (issue #535): plain dicts, bounded LRU, no
    # addon state growth. Process-wide (single-user local server, per #227/#364).
    snapshots = SnapshotStore()

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_project_info() -> ProjectInfo:
        """Get project-level context: name, Godot version, main scene, autoloads,
        and project-defined input actions. Call this to orient before editing.
        """
        return ProjectInfo(**await route(bridge, "cmd_get_project_info"))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_active_scene() -> ActiveScene:
        """Get the currently open scene's path and name. Returns ``is_open=False``
        when no scene is open (not an error).
        """
        return ActiveScene(**await route(bridge, "cmd_get_active_scene"))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def list_scenes() -> ScenesResult:
        """List the project's scene files (``res://*.tscn``) and their editor state —
        which is the ``main_scene``, which are open, and which is active.

        Call this to decide, when no scene is open, whether to OPEN an existing scene
        (a modification / enhancement / bugfix of something already there) or CREATE a
        net-new one:
          - no scenes at all -> the project is empty; create_scene(root_type, path).
          - exactly one scene -> open_scene(that path).
          - several scenes -> open the one the request targets, or ask which to use.
        Returns an empty ``scenes`` list for a project with no scenes yet (not an error).
        """
        return ScenesResult(**await route(bridge, "cmd_list_scenes"))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_scene_tree(max_depth: MaxDepth = -1, lightweight: bool = False) -> SceneTree:
        """Get the open scene as a recursive tree of {name, type, path, script, children}.

        Each node carries an explicit scene-relative ``path`` ("." for the root,
        e.g. "Player/Weapon" below it) — pass it verbatim to set_node_property,
        create_node (as parent_path), attach_script, or get_node_properties; do not
        reconstruct paths by hand.

        ``max_depth`` limits how many child levels are returned (-1 = unlimited,
        0 = root only); use it to avoid huge payloads on deep scenes. ``tree`` is
        null when no scene is open.

        ``lightweight=True`` returns only {name, type, children} (no ``script``) —
        a smaller payload for a discovery pass where you just need the shape; pair
        it with ``max_depth`` to keep large scenes out of context.

        If the full tree exceeds the character limit, a lightweight view is returned
        instead with ``truncated=true`` and a ``hint`` to narrow with ``max_depth``.

        WHEN TO USE: You need to understand the static scene structure before
        making edits (adding nodes, attaching scripts, setting properties).
        WHEN NOT TO USE: The game is running and you need live state — use
        get_game_scene_tree() to read the running game's current hierarchy.
        """
        params = {"max_depth": max_depth, "lightweight": lightweight}
        result = SceneTree(**await route(bridge, "cmd_get_scene_tree", params))
        # Output bounding (issue #222): if the tree is too large, fall back to the
        # lightweight view (a real, addon-supported reduction) and mark it truncated.
        if over_character_limit(result.model_dump_json()):
            if not lightweight:
                light = {"max_depth": max_depth, "lightweight": True}
                result = SceneTree(**await route(bridge, "cmd_get_scene_tree", light))
            result.truncated = True
            result.hint = TRUNCATION_HINT
            # Strict cap: a very wide/deep scene can exceed the limit even when
            # lightweight, so drop the tree entirely rather than return an oversized
            # payload — parity with the resource path's cap_json (#222).
            if over_character_limit(result.model_dump_json()):
                result.tree = None
        return result

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_selected_node() -> SelectedNode:
        """Get the node currently selected in the editor — its path, type, script,
        properties, and child names. Returns ``selected=None`` when nothing is
        selected.
        """
        return SelectedNode(**await route(bridge, "cmd_get_selected_node"))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_node_properties(node_path: str) -> NodeInfo:
        """Get a node's detail by scene-relative path (e.g. "Player/Sprite2D"):
        type, attached script, exported/set properties, and child names. Errors
        with RESOURCE_NOT_FOUND if the path doesn't resolve, or PRECONDITION_FAILED
        if no scene is open.
        """
        return NodeInfo(**await route(bridge, "cmd_get_node_properties", {"node_path": node_path}))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_node_property(node_path: str, property: str) -> NodeProperty:
        """Read a single ``property`` by name from the node at ``node_path`` — including
        **built-in** Godot properties (position, scale, modulate, collision_layer,
        material, theme, …) that ``get_node_properties`` omits (it returns only
        script-declared variables). Returns ``{value, exists}``; ``exists=false``
        (value null) when the node has no such property. The value is JSON-coerced
        (Vector2 as {"x","y"}, Color, NodePath as string). Use it to snapshot a value
        before ``set_node_property`` — for verification or rollback. Errors with
        RESOURCE_NOT_FOUND if the path doesn't resolve, or PRECONDITION_FAILED if no
        scene is open.
        """
        return NodeProperty(
            **await route(
                bridge, "cmd_get_node_property", {"node_path": node_path, "property": property}
            )
        )

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_node_property_list(node_path: str) -> NodePropertyList:
        """Return the flat list of valid property names for the node at
        ``node_path``, plus its runtime class name. Use this to discover what
        properties you can set before calling ``set_node_property``.
        """
        return NodePropertyList(
            **await route(bridge, "cmd_get_node_property_list", {"node_path": node_path})
        )

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def get_node_groups(node_path: str) -> NodeGroups:
        """List the groups the node at ``node_path`` belongs to (``{groups: [name]}``),
        excluding editor-internal groups (names beginning with "_"). Use it to snapshot
        membership before ``add_to_group`` / ``remove_from_group`` (or a delete) so the
        change is reversible. Errors with RESOURCE_NOT_FOUND if the path doesn't resolve,
        or PRECONDITION_FAILED if no scene is open.
        """
        return NodeGroups(**await route(bridge, "cmd_get_node_groups", {"node_path": node_path}))

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def snapshot_subtree(
        node_path: str = ".",
        properties: list[str] | None = None,
        max_depth: MaxDepth = -1,
    ) -> SnapshotResult:
        """Snapshot a subtree as a stable dict (issue #535): node paths, types, script
        paths, and property values (script vars, plus any built-in named in
        ``properties``; empty list = script vars only). Returns a ``snapshot_id``
        that references the server-side store — pass it to ``diff_snapshots`` to
        verify a batch mutation in one round-trip (mutate → diff → assert) instead
        of N re-reads. ``max_depth`` caps depth (-1 = unlimited), like
        ``get_scene_tree``. Errors with RESOURCE_NOT_FOUND if the path doesn't
        resolve, or PRECONDITION_FAILED if no scene is open.
        """
        params = {
            "node_path": node_path,
            "properties": properties or [],
            "max_depth": max_depth,
        }
        body = await route(bridge, "cmd_snapshot_subtree", params)
        tree = body["snapshot"]
        if over_character_limit(SnapshotResult(snapshot_id="x", **body).model_dump_json()):
            raise ToolError(
                f"OUTPUT_LIMIT: snapshot of '{node_path}' exceeds the character limit. "
                f"Narrow with max_depth (current: {max_depth}) or snapshot a smaller subtree."
            )
        snapshot_id = snapshots.put(tree)
        return SnapshotResult(snapshot_id=snapshot_id, **body)

    @mcp.tool(meta=READ_ONLY, tags=INSPECTION)
    async def diff_snapshots(
        before_id: str,
        after_id: str | None = None,
        node_path: str = ".",
    ) -> SnapshotDiff:
        """Diff two subtree snapshots taken with ``snapshot_subtree`` (issue #535):
        ``{added: [node], removed: [node], changed: [{node, property, before, after}]}``.
        All three lists empty means identical. With ``after_id`` unset, the tool
        re-reads the same ``node_path`` live and diffs snapshot-vs-now — the natural
        acceptance check after ``batch_set_property`` / ``apply_node_edits`` /
        ``run_commands``. Errors with RESOURCE_NOT_FOUND for an unknown/evicted id
        (re-snapshot, the store is bounded).
        """
        before = snapshots.get(before_id)
        if before is None:
            raise ToolError(
                f"RESOURCE_NOT_FOUND: unknown or evicted snapshot_id '{before_id}'. "
                "Re-take the snapshot with snapshot_subtree (the store is bounded)."
            )
        if after_id is None:
            body = await route(
                bridge,
                "cmd_snapshot_subtree",
                {"node_path": node_path, "properties": [], "max_depth": -1},
            )
            after = body["snapshot"]
        else:
            after = snapshots.get(after_id)
            if after is None:
                raise ToolError(
                    f"RESOURCE_NOT_FOUND: unknown or evicted snapshot_id '{after_id}'. "
                    "Re-take the snapshot with snapshot_subtree (the store is bounded)."
                )
        diff = diff_trees(before, after)
        return SnapshotDiff(
            added=diff["added"],
            removed=diff["removed"],
            changed=[DiffEntry(**entry) for entry in diff["changed"]],
        )
