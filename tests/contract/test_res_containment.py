"""Contract tests for addon-side res:// containment (issue #909).

The addon's path checks used to be ``begins_with("res://")``, which accepts
``res://../outside.gd`` and ``res:///etc/passwd``. The server's ``ResPath``
(``mcp_server/paths.py::escapes_res_root``) rejects those first; the addon's
check is defense in depth and now routes through one helper,
``MCPHelpers.res_path_error``. The behavioral check is the headless smoke
``godot/tests/res_containment_smoke.gd``; the source scan pins that no bare
``begins_with("res://")`` containment check creeps back in.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
HELPERS_GD = ADDON_DIR / "mcp_helpers.gd"
SMOKE = "res_containment_smoke.gd"
# A scheme test that is not a containment check stays, marked on its line.
SCHEME_MARKER = "scheme test, not containment"
_BARE_CHECK = re.compile(r'begins_with\("res://"\)')


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_res_containment_smoke_helper_and_handlers() -> None:
    """The helper and three handlers refuse escaping paths inside Godot."""
    result = run_godot(["--script", f"res://tests/{SMOKE}"])
    output = result.stdout + result.stderr
    assert "RES_CONTAINMENT_TEST_OK" in output, (
        f"res containment smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_helper_is_defined() -> None:
    src = HELPERS_GD.read_text()
    assert "static func res_path_error(path: String) -> String" in src
    assert "simplify_path()" in src


def test_no_bare_res_prefix_check_outside_helper() -> None:
    """Every res:// containment check goes through the helper."""
    offenders: list[str] = []
    for gd in sorted(ADDON_DIR.rglob("*.gd")):
        if gd == HELPERS_GD:
            continue
        for lineno, line in enumerate(gd.read_text().splitlines(), start=1):
            if _BARE_CHECK.search(line) and SCHEME_MARKER not in line:
                offenders.append(f"{gd.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        'bare begins_with("res://") checks remain; use MCPHelpers.res_path_error '
        f"(or mark a pure scheme test with '# {SCHEME_MARKER}'):\n" + "\n".join(offenders)
    )
