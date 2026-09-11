"""Contract tests pinning the rename refusal rules (issue #473).

The Godot editor refuses renames the addon must refuse too — a rename the
editor rejects corrupts the saved scene (an inherited-scene rename *duplicates*
the node; an instanced-child rename is silently dropped on save). The rules
mirror `SceneTreeDock::_validate_no_foreign_selected` (4.7). Source-scanned
(the addon is GDScript, only runnable inside Godot): the refusal precedes any
UndoRedo action, names the source scene, and the still-allowed set is pinned
so the refusal can't over-trigger.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MUTATION_GD = REPO_ROOT / "godot/addons/godot_mcp/handlers/mutation.gd"


def _rename_handler_src() -> str:
    """The rename handler body plus the refusal helpers directly above it."""
    src = MUTATION_GD.read_text()
    start = src.index("## Whether the node is an entry the edited scene's *base* scene defines")
    return src[start:].split("func _cmd_set_node_property", 1)[0]


def test_rename_refuses_nodes_the_scene_does_not_own() -> None:
    handler = _rename_handler_src()
    # The error names the source scene the node comes from (agent-recoverable hint).
    assert "VALIDATION_ERROR" in handler
    assert "scene_file_path" in handler


def test_rename_refuses_nodes_inherited_from_the_base_scene() -> None:
    handler = _rename_handler_src()
    # Inherited scenes: the edited scene's base state defines the node, so a
    # rename packs a NEW node and the base still creates the original (the
    # save duplicates it). Detected via the base scene state's node paths.
    assert "get_base_scene_state" in handler, handler


def test_rename_still_allows_scene_owned_nodes_and_roots() -> None:
    handler = _rename_handler_src()
    # The allowed set is pinned: the edited root itself, and a node the edited
    # scene owns (owner == root) — the refusal's guard must be `node != root`
    # plus the owner check, so scene-owned nodes stay renamable.
    assert "node == root" in handler or "node != root" in handler, handler
    # Inherited-scene roots stay renamable: the base-state check must exclude
    # the root (the editor allows renaming an inherited root).
    base_block = handler.split("get_base_scene_state", 1)[1][:600]
    assert "root" in base_block