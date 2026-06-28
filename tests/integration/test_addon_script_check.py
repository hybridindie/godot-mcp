"""Headless compile/load gate for every addon script.

Runs ``godot --check-only`` over each ``.gd`` under the addon and fails if any
emits a parse/compile error. This localizes a broken script to a precise file and
message in CI, rather than surfacing only as a plugin-load / bridge-connect
failure in the e2e suites.

Scope note: at the project's default GDScript warning settings this catches hard
parse/compile errors (syntax, undeclared identifiers, bad signatures) — NOT the
"method/property absent on a typed value" class behind #265/#266. That class is an
``unsafe_method_access`` *warning* that GDScript cannot distinguish from the
addon's intentional dynamic access (``Variant`` params, subtype access after an
``is`` check), so it can't be promoted to an error project-wide. The behavioral
safety net for that class is the live e2e suite (#269/#271).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# Substrings that signal a parse/compile failure (and a warning-treated-as-error,
# in case warnings are ever promoted).
_FAIL_MARKERS = ("Parse Error", "Parse error", "Failed to load script", "treated as error")

_ADDON_DIR = GODOT_PROJECT / "addons" / "godot_mcp"


def _res_path(gd_path: Path) -> str:
    return "res://" + gd_path.relative_to(GODOT_PROJECT).as_posix()


def test_all_addon_scripts_compile() -> None:
    scripts = sorted(_ADDON_DIR.rglob("*.gd"))
    assert scripts, "no addon scripts found — wrong path?"

    failures: list[str] = []
    for gd in scripts:
        res = _res_path(gd)
        result = run_godot(["--check-only", "--script", res])
        output = f"{result.stdout}\n{result.stderr}"
        # Primary signal: Godot prints "Parse Error"/"Failed to load script" but still
        # exits 0 on a compile error (see test_gate_catches_a_broken_script), so the
        # markers — not the exit code — are what catch a broken script. A non-zero exit
        # is treated as a failure too, to catch a crash / missing-script / bad invocation
        # that wouldn't print a known marker.
        if result.returncode != 0 or any(marker in output for marker in _FAIL_MARKERS):
            detail = (
                "\n".join(
                    line for line in output.splitlines() if any(m in line for m in _FAIL_MARKERS)
                )
                or f"exit code {result.returncode} with no recognized marker"
            )
            failures.append(f"{res}:\n{detail}")

    assert not failures, "addon scripts failed --check-only:\n\n" + "\n\n".join(failures)


def test_gate_catches_a_broken_script() -> None:
    """Negative control: a script with a real parse error trips the markers — proving the
    gate isn't a silent no-op. (Godot's --check-only exits 0 even here, which is exactly
    why test_all_addon_scripts_compile keys off the markers, not the exit code.)"""
    bad = GODOT_PROJECT / "tests" / "_tmp_broken_check.gd"
    bad.write_text("extends Node\nfunc _ready() ->:\n\tpass\n", encoding="utf-8")
    try:
        result = run_godot(["--check-only", "--script", _res_path(bad)])
        output = f"{result.stdout}\n{result.stderr}"
        assert any(marker in output for marker in _FAIL_MARKERS), (
            f"the gate did not flag a deliberately-broken script:\n{output}"
        )
    finally:
        bad.unlink(missing_ok=True)
        (bad.parent / (bad.name + ".uid")).unlink(missing_ok=True)
