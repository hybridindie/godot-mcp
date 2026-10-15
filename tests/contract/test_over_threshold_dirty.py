"""Contract: over-threshold batch paths mark the scene unsaved (issue #643).

Past the 20-node UndoRedo threshold, `batch_set_property` and
`apply_node_edits` skip UndoRedo — so nothing would set the editor's dirty flag
and the tab would look clean (closing discards the edits). Both paths must call
`EditorInterface.mark_scene_as_unsaved()`.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def test_over_threshold_paths_mark_the_scene_unsaved() -> None:
    for rel in ("handlers/batch.gd", "handlers/composite.gd"):
        src = (_ADDON / rel).read_text(encoding="utf-8")
        assert "mark_scene_as_unsaved()" in src, (
            f"{rel} must mark the scene unsaved on the over-threshold path (#643)"
        )


def test_active_scene_reports_the_dirty_marker() -> None:
    src = (_ADDON / "handlers/scene_inspect.gd").read_text(encoding="utf-8")
    assert "get_unsaved_scenes()" in src and '"dirty"' in src
