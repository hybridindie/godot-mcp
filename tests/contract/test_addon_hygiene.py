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


# Inline JSON -> Vector2 (``Vector2(float(...`` or ``Vector2(d.get(...``), even wrapped.
_INLINE_VECTOR2 = re.compile(r"Vector2\(\s*(?:float\(|d\.get\()")


def _strip_code(line: str) -> str:
    """One GDScript line with string-literal contents blanked and any ``#`` comment
    removed, so a ``#`` or ``print(`` inside a string can't fool the scans."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                quote = ""
                out.append(ch)
            else:
                out.append(" ")
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _strip_lines(lines: list[str]) -> list[str]:
    """Strip each line, blanking the bodies of triple-quoted blocks, which span
    lines (``_strip_code`` alone would rescan them as code)."""
    out: list[str] = []
    in_block = False
    for line in lines:
        if in_block:
            if '"""' in line:
                in_block = False
                out.append(_strip_code(line.split('"""', 1)[1]))
            else:
                out.append("")
            continue
        if line.count('"""') % 2 == 1:
            in_block = True
            out.append(_strip_code(line.split('"""', 1)[0]))
            continue
        out.append(_strip_code(line))
    return out


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Source lines with strings blanked and comments stripped, numbered from 1."""
    raw = path.read_text(encoding="utf-8").splitlines()
    return list(enumerate(_strip_lines(raw), 1))


@pytest.mark.parametrize("path", [PROBE_GD, DEBUGGER_GD], ids=lambda p: p.name)
def test_no_bare_print(path: Path) -> None:
    hits = [f"{path.name}:{n}" for n, code in _code_lines(path) if _BARE_PRINT.search(code)]
    assert not hits, f"bare print() left in addon (use push_warning/push_error): {hits}"


def test_debugger_multi_session_warning_uses_push_warning() -> None:
    source = DEBUGGER_GD.read_text(encoding="utf-8")
    assert re.search(r"push_warning\(\(?\"\[MCPDebugger\] multiple live debugger sessions", source)


def test_input_injection_coerces_through_type_coerce() -> None:
    code = "\n".join(line for _, line in _code_lines(PROBE_GD))
    hits = [
        f"{PROBE_GD.name}:{code.count(chr(10), 0, m.start()) + 1}"
        for m in _INLINE_VECTOR2.finditer(code)
    ]
    assert not hits, f"inline Vector2 coercion (use Coerce.from_json): {hits}"


def test_plugin_header_describes_bridge_as_client() -> None:
    lines = PLUGIN_GD.read_text(encoding="utf-8").splitlines()
    header = " ".join(line.lstrip("#").strip() for line in lines if line.startswith("##"))
    assert "localhost WebSocket server" not in header
    assert "WebSocket client" in header


# -- scanner self-tests (review of #924): the scans must not be fooled by strings --


def test_scanner_keeps_code_after_a_hash_inside_a_string() -> None:
    code = _strip_code('var s := "#abc"; print("dbg")')
    assert _BARE_PRINT.search(code), "a '#' inside a string must not hide the print after it"


def test_scanner_ignores_print_inside_a_string() -> None:
    code = _strip_code('push_warning("use push_error, not print(\\"dbg\\")")')
    assert not _BARE_PRINT.search(code), "print( inside a message string is not a bare print"


def test_scanner_catches_a_wrapped_inline_vector2() -> None:
    src = (
        "motion.relative = Vector2(\n"
        '\tfloat(d.get("relative_x", 0.0)),\n'
        '\tfloat(d.get("relative_y", 0.0))\n'
        ")"
    )
    assert _INLINE_VECTOR2.search("\n".join(_strip_code(line) for line in src.splitlines()))


def test_scanner_blanks_triple_quoted_blocks() -> None:
    lines = _strip_lines(['const SRC := """', "\tprint(message)", '"""', 'print("x")'])
    assert not _BARE_PRINT.search(lines[1]), 'a print inside a """ block is string text'
    assert _BARE_PRINT.search(lines[3]), "code after the block is scanned again"


def test_scanner_catches_a_cast_free_inline_vector2() -> None:
    code = 'motion.relative = Vector2(d.get("relative_x", 0.0), d.get("relative_y", 0.0))'
    assert _INLINE_VECTOR2.search(_strip_code(code))
