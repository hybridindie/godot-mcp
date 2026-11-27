"""Source-level hygiene contract for the addon (issue #911).

The addon logs through ``push_warning``/``push_error`` (they reach the editor's
Errors panel and carry a stack), coerces JSON to Godot types only through
``type_coerce.gd`` (``addon.md``), and its header describes the bridge as the
WebSocket *client* it has been since #276. ``validation_runner.gd`` and
``project_tools_runner.gd`` are deliberately out of scope: their ``print`` calls
are the stdout protocol the headless subprocess runners parse.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
PROBE_GD = ADDON_DIR / "mcp_runtime_probe.gd"
DEBUGGER_GD = ADDON_DIR / "mcp_debugger.gd"
PLUGIN_GD = ADDON_DIR / "godot_mcp.gd"

# A bare ``print(`` call, not ``push_warning(``/``printerr(``/``obj.print(``.
_BARE_PRINT = re.compile(r"(?<![\w.])print\(")


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Source lines with ``#`` comments stripped, numbered from 1."""
    return [
        (n, line.split("#", 1)[0])
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
    ]


@pytest.mark.parametrize("path", [PROBE_GD, DEBUGGER_GD], ids=lambda p: p.name)
def test_no_bare_print(path: Path) -> None:
    hits = [f"{path.name}:{n}" for n, code in _code_lines(path) if _BARE_PRINT.search(code)]
    assert not hits, f"bare print() left in addon (use push_warning/push_error): {hits}"


def test_debugger_multi_session_warning_uses_push_warning() -> None:
    source = DEBUGGER_GD.read_text(encoding="utf-8")
    assert re.search(r"push_warning\(\(?\"\[MCPDebugger\] multiple live debugger sessions", source)


def test_input_injection_coerces_through_type_coerce() -> None:
    hits = [f"{PROBE_GD.name}:{n}" for n, code in _code_lines(PROBE_GD) if "Vector2(float(" in code]
    assert not hits, f"inline Vector2 coercion (use Coerce.from_json): {hits}"


def test_plugin_header_describes_bridge_as_client() -> None:
    lines = PLUGIN_GD.read_text(encoding="utf-8").splitlines()
    header = " ".join(line.lstrip("#").strip() for line in lines if line.startswith("##"))
    assert "localhost WebSocket server" not in header
    assert "WebSocket client" in header
