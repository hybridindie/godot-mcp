"""Regression guard for the set_resource_property UndoRedo target (#263/#268).

``_set_and_save_resource`` is defined on the command router, not on the resources
handler. The handler must register its UndoRedo do/undo against ``_router`` — if it
targets ``self`` (as it once did), the method resolves to nothing and the set
silently never runs.

The addon is GDScript and can't execute in CI (no editor), so this pins the fix
at the source level instead — cheap, CI-runnable, and enough to catch a
reintroduction of the wrong-target bug.
"""

from __future__ import annotations

from pathlib import Path

_RESOURCES_GD = (
    Path(__file__).resolve().parents[2]
    / "godot"
    / "addons"
    / "godot_mcp"
    / "handlers"
    / "resources.gd"
)


def test_set_resource_property_undoredo_targets_router() -> None:
    src = _RESOURCES_GD.read_text(encoding="utf-8")
    # Must invoke the router-defined helper on _router...
    assert 'add_do_method(_router, "_set_and_save_resource"' in src
    assert 'add_undo_method(_router, "_set_and_save_resource"' in src
    # ...and never on self (where the method does not exist → silent no-op).
    assert 'add_do_method(self, "_set_and_save_resource"' not in src
    assert 'add_undo_method(self, "_set_and_save_resource"' not in src
