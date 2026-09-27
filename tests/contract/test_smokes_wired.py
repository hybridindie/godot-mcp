"""Contract test: every godot/tests/*_smoke.gd is wired into pytest (#578).

Smoke scripts are the behavioral evidence the addon source cites (probe
comments reference input_inject_smoke.gd as the #201 verification, etc.) — but
wiring is manual, and seven smokes (auth, auto_refresh, csharp, extract,
input_inject, move_file, probe_change) sat unverified in CI for their whole
life until the #578 sweep. This test makes "unwired" fail the suite instead:
each smoke script must be referenced by some test module under tests/.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GODOT_TESTS = REPO_ROOT / "godot" / "tests"
TESTS_DIR = REPO_ROOT / "tests"

# Smokes driven by their own dedicated test file (run_godot in a contract or
# integration test, not the SMOKES parametrization).
_DEDICATED_WIRING = {
    "bridge_reconnect_smoke.gd": "integration/test_addon_bridge_reconnect.py",
    "bridge_smoke.gd": "integration/test_addon_bridge.py",
    "dock_smoke.gd": "integration/test_addon_dock.py",
    "inspect_smoke.gd": "integration/test_addon_inspect.py",
    "screenshot_smoke.gd": "integration/test_addon_screenshot.py",
    "guards_smoke.gd": "contract/test_addon_guards.py",
    "handshake_smoke.gd": "contract/test_addon_handshake.py",
    "helpers_smoke.gd": "contract/test_router_refactor.py",
    "threshold_smoke.gd": "contract/test_undo_threshold.py",
}


def _all_test_sources() -> str:
    return "\n".join(p.read_text() for p in TESTS_DIR.rglob("*.py"))


def test_every_smoke_script_is_wired_into_pytest() -> None:
    sources = _all_test_sources()
    unwired: list[str] = []
    for path in sorted(GODOT_TESTS.glob("*_smoke.gd")):
        name = path.name
        in_smokes = f'"{name}"' in sources or f"'{name}'" in sources
        has_dedicated = (
            name in _DEDICATED_WIRING and (TESTS_DIR / _DEDICATED_WIRING[name]).exists()
        )
        wired = in_smokes or has_dedicated
        if not wired:
            unwired.append(name)
    assert not unwired, (
        f"unwired smoke scripts (CI never runs them): {unwired}. "
        "Add each to SMOKES in tests/integration/test_addon_read_smokes.py or "
        "give it a dedicated run_godot test — a smoke that CI doesn't run "
        "cannot catch regressions (#578)."
    )


def test_dedicated_wiring_files_exist() -> None:
    """The dedicated-wiring map must not rot (renamed/deleted test files)."""
    for name, test_file in _DEDICATED_WIRING.items():
        assert (TESTS_DIR / test_file).exists(), (
            f"{name} maps to missing test file {test_file}"
        )