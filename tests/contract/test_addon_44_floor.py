"""Contract: the addon parses on the Godot 4.4 floor (#738).

`EditorInterface.get_unsaved_scenes()` is Godot 4.7+. A static call makes the
whole addon unparseable on 4.4–4.6 (handlers preload at parse time), which the
real 4.4 CI lane now catches. Calls must stay dynamic so the floor is real.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def test_no_addon_source_calls_get_unsaved_scenes_statically() -> None:
    offenders = sorted(
        str(path.relative_to(_ADDON))
        for path in _ADDON.rglob("*.gd")
        if "EditorInterface.get_unsaved_scenes(" in path.read_text(encoding="utf-8")
    )
    assert not offenders, (
        "a static EditorInterface.get_unsaved_scenes() call breaks the 4.4 floor "
        f"(#738); call it dynamically instead: {offenders}"
    )


def test_helper_resolves_unsaved_scenes_dynamically() -> None:
    src = (_ADDON / "mcp_helpers.gd").read_text(encoding="utf-8")
    assert 'EditorInterface.has_method("get_unsaved_scenes")' in src
    assert 'EditorInterface.call("get_unsaved_scenes")' in src
    assert "func unsaved_scenes() -> Variant" in src


def test_scene_move_falls_back_to_open_scenes_on_the_floor() -> None:
    src = (_ADDON / "handlers/project_fs.gd").read_text(encoding="utf-8")
    # 4.4–4.6 cannot report dirty state — refuse moving any open scene instead.
    assert "unsaved_scenes()" in src
    assert "EditorInterface.get_open_scenes()" in src
