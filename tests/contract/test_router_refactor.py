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

import re
from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

ADDON_DIR = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
ROUTER_GD = ADDON_DIR / "command_router.gd"
HELPERS_GD = ADDON_DIR / "mcp_helpers.gd"
HANDLERS_DIR = ADDON_DIR / "handlers"

_HANDLER_PRELOAD = re.compile(r'preload\("\./handlers/([a-z0-9_]+)\.gd"\)')


def _router_src() -> str:
    return ROUTER_GD.read_text()


def _function_body(src: str, name: str) -> str:
    """The body of ``func name(...)`` up to the next top-level function."""
    start = src.index(f"func {name}(")
    end = src.find("\nfunc ", start + 1)
    return src[start:] if end == -1 else src[start:end]


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
    """The router wires handlers through one table loop, and ``dispose()`` clears
    only the real references. Behavior (every domain registered, commands live)
    is pinned by ``helpers_smoke.gd``; these checks enforce the architecture that
    behavior cannot observe."""
    src = _router_src()
    init = _function_body(src, "_init")
    assert "for handler_script in HANDLERS:" in init
    assert init.count("handler.register(_handlers)") == 1
    assert "_instances.append(handler)" in init
    assert init.count("handler_script.new(self)") == 1, (
        "router still constructs domain handlers outside the HANDLERS loop"
    )

    dispose = _function_body(src, "dispose")
    for attr in ("_handlers", "_instances"):
        assert f"{attr}.clear()" in dispose, f"dispose() must clear {attr}"
    for attr in ("_debugger", "_helpers", "_guards"):
        assert f"{attr} = null" in dispose, f"dispose() must drop {attr}"

    # No per-domain member vars: discover the handler class names from the
    # scripts themselves instead of hard-coding a stale list.
    handler_classes = {
        match.group(1)
        for path in HANDLERS_DIR.glob("*.gd")
        if (match := re.search(r"^class_name (MCP\w+)$", path.read_text(), re.M))
    }
    for cls in sorted(handler_classes):
        assert f": {cls}" not in src, (
            f"router keeps a per-domain member of type {cls} — "
            "registration must be data-driven (#522)"
        )


def test_handler_table_covers_every_domain() -> None:
    """The HANDLERS table is derived from the handler scripts on disk: every
    ``handlers/*.gd`` file appears exactly once, and nothing stale remains."""
    src = _router_src()
    table = _HANDLER_PRELOAD.findall(src)
    on_disk = sorted(path.stem for path in HANDLERS_DIR.glob("*.gd"))
    assert sorted(table) == on_disk, (
        "router HANDLERS table and handlers/ disagree: "
        f"table-only={sorted(set(table) - set(on_disk))}, "
        f"disk-only={sorted(set(on_disk) - set(table))}"
    )
    assert len(table) == len(set(table)), "HANDLERS table has a duplicate entry"
    # The loop drives registration (one register call site).
    assert src.count(".register(") == 1, (
        "router must register handlers in one loop, not inline calls"
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