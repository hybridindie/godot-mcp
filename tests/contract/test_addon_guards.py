"""Contract tests for the unified probe/break precondition guards (issue #527).

The addon has three guard flavors scattered across two files with drifted
shapes: ``command_router.gd``'s ``_require_debug_session`` /
``_require_live_probe``, and ``runtime_session.gd``'s inline re-implementation
in ``_cmd_get_game_scene_tree`` that carries the richer #454 diagnostic
(``probe_never_connected`` + the "max client limits reached" hint) the shared
helper does not produce. Only ``get_game_scene_tree`` returns that diagnostic
today — every other probe-gated handler returns the generic
"The godot_mcp runtime probe is not connected" line, which cannot disambiguate
"forgot the autoload" from "engine session caps exhausted after play/stop
cycles" (#454).

Consolidation contract: one guard module (``mcp_guards.gd``) with composable
``play_session`` / ``debug_session`` / ``live_probe`` / ``unpaused`` checks;
every probe-gated handler routes through it, and every probe-never-connected
failure carries the #454 diagnostic. Source-scanned (the addon is GDScript,
only runnable inside Godot — per ``test_rename_refusal.py``); the live
behavioral check is ``godot/tests/guards_smoke.gd`` via the e2e runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
GUARDS_GD = ADDON_DIR / "mcp_guards.gd"
ROUTER_GD = ADDON_DIR / "command_router.gd"
RUNTIME_SESSION_GD = ADDON_DIR / "handlers" / "runtime_session.gd"


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_guards_smoke_pins_the_envelope() -> None:
    """The headless smoke asserts the real guard envelopes inside Godot."""
    result = run_godot(["--script", "res://tests/guards_smoke.gd"])
    output = result.stdout + result.stderr
    assert "GUARDS_TEST_OK" in output, (
        f"guards smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_guards_live_in_one_module() -> None:
    """One guard module exists; the router's wrappers are pure delegation."""
    assert GUARDS_GD.is_file(), (
        f"missing consolidated guard module at {GUARDS_GD} (issue #527)"
    )
    src = GUARDS_GD.read_text()
    for guard in (
        "require_play_session",
        "require_debug_session",
        "require_live_probe",
        "require_unpaused_live_probe",
    ):
        assert f"func {guard}" in src, f"{GUARDS_GD.name} missing {guard}"
    # The router hosts DELEGATING WRAPPERS (call-site compatibility) but no
    # guard logic: its two wrappers are two-line delegates to the module.
    router_src = ROUTER_GD.read_text()
    for wrapper in ("func _require_debug_session", "func _require_live_probe"):
        assert wrapper in router_src  # call sites unchanged
        body = router_src.split(wrapper, 1)[1].split("func ", 1)[0]
        assert "EditorInterface" not in body and "is_playing" not in body, (
            f"router {wrapper} still owns guard logic — must delegate to mcp_guards.gd"
        )


def test_no_handler_reimplements_guards_inline() -> None:
    """runtime_session routes through the guard module (its inline copy gone).

    get_game_scene_tree is the deliberate exception to the hard-guard rule: a
    read-only poll tool reports state (a soft {playing, connected: false}
    result) instead of refusing, so it keeps a *play-session-only* guard check
    but consumes the #454 hint text from the guard module — the refusal-hint
    logic is not inline.
    """
    src = RUNTIME_SESSION_GD.read_text()
    handler = src.split("func _cmd_get_game_scene_tree", 1)[1].split("func ", 1)[0]
    # The hint is single-sourced from the guard module (the inline text is gone):
    assert "probe_never_connected_hint()" in handler, (
        "runtime_session._cmd_get_game_scene_tree must consume the #454 hint "
        "from mcp_guards.gd, not inline the text"
    )
    assert "max client limits" not in handler
    assert "mcp_runtime_probe.gd" not in handler
    # The play-session check routes through the guard module:
    assert "require_play_session()" in handler


def test_every_probe_gated_failure_carries_the_454_diagnostic() -> None:
    """The probe-never-connected diagnostic (#454) ships from the shared guard,
    so every probe-gated handler surfaces the "max client limits reached"
    recovery hint — not just get_game_scene_tree."""
    guards_src = GUARDS_GD.read_text()
    assert "max client limits" in guards_src, (
        "the #454 recovery diagnostic must live in mcp_guards.gd (issue #527)"
    )
    assert "probe_never_connected_hint" in guards_src
    # The old inline copy in runtime_session is gone (one implementation).
    session_src = RUNTIME_SESSION_GD.read_text()
    # The soft-result field name legitimately stays (get_game_scene_tree's
    # documented response shape) — what must be gone is the inline hint TEXT.
    assert "max client limits" not in session_src
    assert "mcp_runtime_probe.gd) as an autoload" not in session_src
    # The old generic-only guard text on the router is gone.
    router_src = ROUTER_GD.read_text()
    assert "probe is not connected; add it as an autoload" not in router_src


def test_guard_failures_use_enumerated_codes_and_required_field() -> None:
    """Guard failures are structured preconditions with a `required` key."""
    src = GUARDS_GD.read_text()
    assert "PRECONDITION_FAILED" in src
    assert '"runtime_probe"' in src or '"play_session"' in src
    # The unpaused guard keeps the #443 break-gate refusal.
    assert "game_not_breaked" in src