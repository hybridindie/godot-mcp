"""Contract tests for the router refactor (issue #522): data-driven handler
registration + the shared-helpers module.

The router grew to ~800 lines of boilerplate: 31 preloads, 30 member vars, 30
``X.new(self) + register()`` pairs in ``_init()``, and a 30-line ``dispose()``
clearing each member by hand — four triplicated edits per new domain. Handlers
simultaneously reach into ~20 router *private* methods (``_resolve``,
``_property_type``, ``_persistent_target``, file I/O, persistence truth, ...),
so the router became a helpers grab-bag rather than pure dispatch, and the
handler↔router back-references form the RefCounted cycle ``dispose()`` exists
to break.

Target contract:
1. **Data-driven registration** — a single const table of
   ``[preload, ...]`` entries wired in one loop; ``dispose()`` is trivial
   (``_handlers.clear()`` + nulling the few real references), and adding a new
   domain handler is one table entry, not four edits.
2. **One helpers module** (``mcp_helpers.gd``) owns the shared logic — file
   I/O, node resolution, property-type cache, persistence truth, instantiation
   validation, batch-threshold decision — and handlers consume it directly.
3. The router stays dispatch + envelope builders + router-owned commands
   (ping/undo/run_commands/project-info/handshake).

Source-scanned per the established pattern (the addon is GDScript); live
behavior is pinned by the existing smoke suite (bridge/run_commands/handshake/
guards/threshold smokes all exercise the router) plus a new helpers smoke.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

ADDON_DIR = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
ROUTER_GD = ADDON_DIR / "command_router.gd"
HELPERS_GD = ADDON_DIR / "mcp_helpers.gd"

HANDLER_TABLE = [
    "scene_inspect", "mutation", "scripts", "node_parity", "animation",
    "physics", "scene_3d", "mesh_library", "particles", "navigation",
    "audio", "tilemap", "tileset", "theme_ui", "shaders", "runtime_session",
    "runtime_inspect", "input_recording", "profiling", "batch", "composite",
    "export", "editor", "project_fs", "resources", "scene_session",
    "input_map", "debugger", "import_asset", "visual_shader", "project_scaffold",
]


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


def test_router_registration_is_data_driven() -> None:
    """Adding a domain costs one table entry, not four edits: no per-domain
    preload/member-var/new/register/dispose boilerplate survives."""
    src = _router_src()
    # No per-domain member variables (the cycle-keeping members die).
    for name in (
        "_scene_inspect", "_mutation", "_scripts", "_node_parity",
        "_animation", "_physics", "_scene_3d", "_mesh_library",
        "_particles", "_navigation", "_audio", "_tilemap", "_tileset",
        "_theme_ui", "_shaders", "_runtime_session", "_runtime_inspect",
        "_input_recording", "_profiling", "_batch", "_composite", "_export",
        "_editor", "_project_fs", "_resources", "_scene_session",
        "_input_map", "_debugger_handlers", "_import_asset", "_visual_shader",
    ):
        assert f"var {name}: MCP" not in src, (
            f"router keeps a per-domain member var {name} — registration must be data-driven (#522)"
        )
    # No per-domain .new(self)+register lines in _init.
    assert src.count("= MCP") <= 2, (
        "router still constructs domain handlers inline — use the HANDLERS table loop"
    )
    # dispose() is trivial (no 30-line member-clearing).
    dispose = src[src.index("func dispose") :]
    dispose = dispose[: dispose.index("\nfunc ", 1)]
    assert dispose.count("= null") <= 3, (
        "dispose() still clears per-domain members by hand — must be trivial (#522)"
    )


def test_handler_table_covers_every_domain() -> None:
    """The HANDLERS table lists all 31 domain handler scripts (plus guards)."""
    src = _router_src()
    for domain in HANDLER_TABLE:
        assert f'"{domain}' in src or f"{domain}" in src, (
            f"router HANDLERS table missing the {domain} domain (#522)"
        )
    # And the loop drives registration (a single register call site).
    assert src.count(".register(") <= 1, (
        "router must register handlers in one loop, not 30 inline calls"
    )


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


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_helpers_smoke_pins_the_behavior() -> None:
    """The headless smoke exercises the helpers module + the data-driven router."""
    result = run_godot(["--script", "res://tests/helpers_smoke.gd"])
    output = result.stdout + result.stderr
    assert "HELPERS_TEST_OK" in output, (
        f"helpers smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output