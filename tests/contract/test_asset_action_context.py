"""Contract test: non-scene asset edits route into the scene history (issue #640).

Script/resource/shader/file edits create an undo action whose first bound object
is the router (not a Node), so `EditorUndoRedoManager` puts it in the **global**
history — and `godot_undo` (which reads the edited scene's history) reverts an
earlier *scene* edit instead. Each such `create_action` must pass the edited
scene root as `custom_context` (`_router.asset_action_context()`).
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"

# handler file -> a distinctive snippet of the create_action line that must carry
# the scene context.
_ASSET_ACTIONS = {
    "handlers/scripts.gd": '"Write script %s" % path',
    "handlers/resources.gd": '"Set %s.%s" % [path.get_file(), property]',
    "handlers/shaders.gd": '"Create shader %s" % path',
    "handlers/visual_shader.gd": '"Create visual shader"',
    "handlers/project_fs.gd": '"Delete file %s" % path',
}


def test_router_exposes_asset_action_context() -> None:
    src = (_ADDON / "command_router.gd").read_text(encoding="utf-8")
    assert "func asset_action_context()" in src
    assert "get_edited_scene_root()" in src


def test_asset_edits_pass_the_scene_context() -> None:
    problems: list[str] = []
    for rel, snippet in _ASSET_ACTIONS.items():
        src = (_ADDON / rel).read_text(encoding="utf-8")
        line = next(
            (ln for ln in src.splitlines() if snippet in ln and "create_action(" in ln), None
        )
        if line is None:
            problems.append(f"{rel}: create_action line not found for {snippet}")
        elif "asset_action_context()" not in line:
            problems.append(f"{rel}: missing asset_action_context() on {line.strip()}")
    assert not problems, (
        "asset edits must route to the scene history (#640):\n" + "\n".join(problems)
    )
