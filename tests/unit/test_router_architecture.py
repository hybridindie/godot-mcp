"""Architecture guards for the router refactor (issue #522).

These inspect the GDScript source because the addon only runs inside Godot:
they pin where the shared logic lives and that router wrappers stay pure
delegates. They are *not* behavior contracts — behavioral coverage lives in
``tests/contract/test_router_refactor.py`` (``helpers_smoke.gd``), which
instantiates the router and exercises registration + helpers at runtime.
"""

from __future__ import annotations

from pathlib import Path

ADDON_DIR = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
ROUTER_GD = ADDON_DIR / "command_router.gd"
HELPERS_GD = ADDON_DIR / "mcp_helpers.gd"


def _router_src() -> str:
    return ROUTER_GD.read_text()


def test_helpers_module_exists_and_owns_the_shared_logic() -> None:
    """One helpers module owns the logic that used to live on the router."""
    assert HELPERS_GD.is_file(), f"missing helpers module at {HELPERS_GD}"
    src = HELPERS_GD.read_text()
    # The moved helper families (one representative each):
    for helper in (
        "func resolve_node",           # node resolution (was _resolve)
        "func property_type",          # property-type cache
        "func persistent_target",      # persistence truth (#477)
        "func commit_add_child",       # shared add-child undo commit
        "func write_file_text",        # file I/O family
        "func instantiate_validated",  # ClassDB instantiation
        "func undoable_for_count",     # #523 threshold decision
        "func undo_threshold_hint",    # #523 hint
    ):
        assert helper in src, f"{HELPERS_GD.name} missing {helper}"


def test_handlers_use_the_helpers_module_not_router_privates() -> None:
    """Handlers consume mcp_helpers.gd for shared logic; the router exposes only
    the envelope builders (_ok/_fail) and dispatch state (_handlers, _route,
    _debugger) as its still-intentional shared surface. Every router helper is
    a one-line delegate to _helpers."""
    helpers_src = HELPERS_GD.read_text()
    router_src = _router_src()
    moved = (
        "resolve_node", "property_type", "persistent_target",
        "commit_add_child", "write_file_text", "instantiate_validated",
    )
    for helper in moved:
        # The implementation lives in the helpers module...
        assert helper in helpers_src
    # ...and every router wrapper for the moved families delegates (the call
    # sites read unchanged; the logic does not live on the router).
    for wrapper in (
        "func _resolve", "func _property_type", "func _persistent_target",
        "func _commit_add_child(", "func _write_file_text", "func _instantiate_validated",
    ):
        assert wrapper in router_src, f"router lost its {wrapper} delegate"
        fn = router_src[router_src.index(wrapper):]
        fn = fn[: fn.index("\nfunc ", 1)] if "\nfunc " in fn else fn
        delegate_lines = [line for line in fn.splitlines() if "_helpers." in line]
        assert len(delegate_lines) >= 1, f"{wrapper} does not delegate to _helpers"
        # No logic keywords in the delegate: the body must be pure forwarding.
        logic = [line for line in fn.splitlines()
                 if ("EditorInterface" in line or "ClassDB" in line or "DirAccess" in line
                     or "FileAccess" in line or "ResourceLoader" in line
                     or "ProjectSettings" in line or "get_edited_scene_root" in line)]
        assert not logic, f"{wrapper} still owns editor logic (#522): {logic}"
