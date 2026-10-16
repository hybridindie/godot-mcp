"""Contract: cross_scene_set_property safety (issue #645).

The handler must (a) refuse any scene open in a tab — active OR background — so an
on-disk edit can't be overwritten by that tab's next save, (b) only change nodes
owned by the scene (instance internals don't persist), and (c) repack the cached
resource so the resource cache isn't left serving the old version.
"""

from __future__ import annotations

from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[2]
    / "godot"
    / "addons"
    / "godot_mcp"
    / "handlers"
    / "batch.gd"
).read_text(encoding="utf-8")


def test_refuses_any_scene_open_in_a_tab() -> None:
    assert "get_open_scenes()" in _SRC, "must refuse scenes open in any tab (#645)"
    assert "open in a tab" in _SRC


def test_only_owned_nodes_are_changed() -> None:
    # The owner filter keeps instance internals (owner != root) out of the set.
    assert "node.owner == root" in _SRC


def test_repacks_the_cached_resource() -> None:
    # `packed.pack(root)` updates the cached resource; a fresh PackedScene would
    # leave the cache stale.
    assert "packed.pack(root)" in _SRC
    assert "PackedScene.new()" not in _SRC
