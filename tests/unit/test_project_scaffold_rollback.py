"""Guards for the project-scaffold rollback edges (#700 review).

The live e2e test forces a mid-scaffold failure and checks the main rollback
path. These pin the two sidecar/cache edges that are hard to force in e2e:
pre-existing `.uid` sidecars and the raw project.godot fallback.
"""

from __future__ import annotations

from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[2]
    / "godot"
    / "addons"
    / "godot_mcp"
    / "handlers"
    / "project_scaffold.gd"
).read_text(encoding="utf-8")


def test_rollback_snapshots_and_restores_uid_sidecars() -> None:
    assert '"uid_existed"' in _SRC
    assert '"uid_text"' in _SRC
    assert '_write_text(uid_path, str(state["uid_text"]))' in _SRC
    assert "DirAccess.remove_absolute(uid_path)" in _SRC


def test_raw_project_file_fallback_refreshes_the_editor_view() -> None:
    assert "EditorInterface.get_resource_filesystem().update_file(PROJECT_FILE)" in _SRC
