"""Contract: autoload register/unregister validate + surface errors (issue #646).

The autoload handlers wrote `autoload/*` settings directly. Two concrete gaps are
pinned here: an invalid identifier name is refused, and a `ProjectSettings.save()`
failure is surfaced (not swallowed).
"""

from __future__ import annotations

from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[2]
    / "godot"
    / "addons"
    / "godot_mcp"
    / "handlers"
    / "resources.gd"
).read_text(encoding="utf-8")


def test_autoload_name_must_be_an_identifier() -> None:
    assert "is_valid_identifier()" in _SRC, "autoload names must be validated (#646)"


def test_save_errors_are_surfaced() -> None:
    assert "var save_err := ProjectSettings.save()" in _SRC
    assert "Failed to save project settings" in _SRC
    # The bare ignored call form must be gone.
    assert "\tProjectSettings.save()\n" not in _SRC


def test_autoload_handlers_use_the_editor_api_when_available() -> None:
    """#700: the editor API supplies undo + Autoload panel refresh."""
    assert "_router.add_autoload_singleton(" in _SRC
    assert "_router.remove_autoload_singleton(" in _SRC
    assert "_router.has_plugin()" in _SRC
    router = (
        Path(__file__).resolve().parents[2]
        / "godot"
        / "addons"
        / "godot_mcp"
        / "command_router.gd"
    ).read_text(encoding="utf-8")
    assert "func set_plugin(plugin: EditorPlugin)" in router
    assert "func add_autoload_singleton(name: String, path: String)" in router
    assert "func remove_autoload_singleton(name: String)" in router
    entry = (
        Path(__file__).resolve().parents[2]
        / "godot"
        / "addons"
        / "godot_mcp"
        / "godot_mcp.gd"
    ).read_text(encoding="utf-8")
    assert "router.set_plugin(self)" in entry
