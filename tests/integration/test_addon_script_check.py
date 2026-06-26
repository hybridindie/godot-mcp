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
        if any(marker in output for marker in _FAIL_MARKERS):
            detail = "\n".join(
                line for line in output.splitlines() if any(m in line for m in _FAIL_MARKERS)
            )
            failures.append(f"{res}:\n{detail}")

    assert not failures, "addon scripts failed --check-only:\n\n" + "\n\n".join(failures)
