"""Contract test: simulated keys match physical-keycode Input Map bindings (#570).

The addon is GDScript and cannot run outside Godot, so the CI-runnable gate is a
source scan (the pattern of ``test_addon_guards.py``); the live behavioral check
is ``godot/tests/key_binding_smoke.gd`` via the e2e runner.

Godot 4's Input Map editor binds actions by PHYSICAL keycode by default. The
probe's ``_inject_key`` (godot/addons/godot_mcp/mcp_runtime_probe.gd) sets only
``event.keycode`` — and an InputEventKey carrying only ``keycode`` never matches
a physical-keycode binding (docs: comparison is keycode → physical_keycode,
first match wins; real hardware events populate both). The fix contract: the
injector sets BOTH ``keycode`` and ``physical_keycode`` (same Key), so injected
keys match both binding types exactly like real hardware events.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_GD = REPO_ROOT / "godot" / "addons" / "godot_mcp" / "mcp_runtime_probe.gd"


def test_inject_key_sets_both_keycodes() -> None:
    src = PROBE_GD.read_text()
    handler = src.split("func _inject_key", 1)[1].split("func ", 1)[0]
    assert "event.keycode = " in handler, "_inject_key must set keycode"
    assert "event.physical_keycode = " in handler, (
        "_inject_key must set physical_keycode too — actions bound by physical "
        "keycode (the Input Map editor's default) otherwise never fire (#570)"
    )


def test_key_binding_smoke_is_wired_into_pytest() -> None:
    """The behavioral smoke runs in CI on the self-hosted e2e runner."""
    from tests.integration.test_addon_read_smokes import SMOKES

    assert ("key_binding_smoke.gd", "KEY_BINDING_TEST_OK") in SMOKES