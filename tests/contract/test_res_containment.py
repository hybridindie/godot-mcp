"""Contract tests for addon-side res:// containment (issue #909).

The addon's path checks used to be ``begins_with("res://")``, which accepts
``res://../outside.gd`` and ``res:///etc/passwd``. The server's ``ResPath``
(``mcp_server/paths.py::escapes_res_root``) rejects those first; the addon's
check is defense in depth and now routes through one helper,
``MCPPaths.res_path_error`` (a dependency-free leaf script; ``MCPHelpers``
delegates to it). The behavioral check is the headless smoke
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
PATHS_GD = ADDON_DIR / "mcp_paths.gd"
COERCE_GD = ADDON_DIR / "type_coerce.gd"
SMOKE = "res_containment_smoke.gd"
# A scheme test that is not a containment check stays, marked on its line.
SCHEME_MARKER = "scheme test, not containment"
_BARE_CHECK = re.compile(r'begins_with\("res://"\)')


def _code_lines(src: str) -> str:
    """The source without whole-line comments (doc comments may name APIs)."""
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_res_containment_smoke_helper_and_handlers() -> None:
    """The helper and every path-taking handler refuse escaping paths in Godot."""
    result = run_godot(["--script", f"res://tests/{SMOKE}"])
    output = result.stdout + result.stderr
    assert "RES_CONTAINMENT_TEST_OK" in output, (
        f"res containment smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_helper_is_a_leaf_with_its_own_normaliser() -> None:
    """The normaliser lives in a dependency-free leaf and never calls simplify_path.

    ``String.simplify_path()`` collapses repeated leading ``..`` differently
    across engine versions, so on the 4.4 floor ``res://../../x`` could pass.
    """
    src = PATHS_GD.read_text()
    code = _code_lines(src)
    assert "class_name MCPPaths" in src
    assert "static func res_path_error(path: String) -> String" in src
    assert "simplify_path" not in code
    assert "preload(" not in code and "MCPHelpers" not in code
    assert (ADDON_DIR / "mcp_paths.gd.uid").exists()


def test_helpers_delegate_and_coerce_avoids_the_cycle() -> None:
    """MCPHelpers keeps the contract name; type_coerce calls the leaf directly."""
    helpers = HELPERS_GD.read_text()
    assert "static func res_path_error(path: String) -> String" in helpers
    assert "MCPPaths.res_path_error(path)" in helpers
    assert "simplify_path" not in _code_lines(helpers)
    coerce = _code_lines(COERCE_GD.read_text())
    assert "MCPHelpers" not in coerce
    assert "MCPPaths." in coerce


def test_no_bare_res_prefix_check_outside_helper() -> None:
    """Every res:// containment check goes through the helper."""
    offenders: list[str] = []
    for gd in sorted(ADDON_DIR.rglob("*.gd")):
        if gd == PATHS_GD:
            continue
        for lineno, line in enumerate(gd.read_text().splitlines(), start=1):
            if _BARE_CHECK.search(line) and SCHEME_MARKER not in line:
                offenders.append(f"{gd.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        'bare begins_with("res://") checks remain; use MCPHelpers.res_path_error '
        f"(or mark a pure scheme test with '# {SCHEME_MARKER}'):\n" + "\n".join(offenders)
    )
