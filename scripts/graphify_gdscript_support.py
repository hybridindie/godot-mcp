#!/usr/bin/env python3
"""Add GDScript (.gd) support to the installed graphify package.

graphify ships tree-sitter extractors for ~40 languages but not GDScript, so the
Godot addon half of this MCP (godot/addons/godot_mcp/*.gd) is invisible to the
knowledge graph. This patcher teaches the *installed* graphify to parse .gd:

  1. installs `tree-sitter-language-pack` (bundles the gdscript grammar);
  2. writes a `tree_sitter_gdscript` shim exposing the grammar as `language()`;
  3. patches graphify/detect.py  — adds `.gd` to CODE_EXTENSIONS;
  4. patches graphify/extract.py — a GDScript LanguageConfig + dispatch entry,
     a positional-callee branch (GDScript calls have no named callee field), and
     a one-line fix so a provider returning a Language (not a capsule) works.

Idempotent: re-running is a no-op. site-packages edits are wiped by
`graphify install`/upgrades — just re-run this script afterward (it's committed
so the support is reproducible). Run with the SAME interpreter graphify uses,
e.g.  `<graphify-python> scripts/graphify_gdscript_support.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _ensure_language_pack() -> None:
    try:
        import tree_sitter_language_pack  # noqa: F401
        return
    except ImportError:
        pass
    print("installing tree-sitter-language-pack …")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "tree-sitter-language-pack>=1.8"],
        check=True,
    )


def _write_shim(site_dir: Path) -> None:
    shim = site_dir / "tree_sitter_gdscript.py"
    body = (
        '"""Shim: expose the language-pack GDScript grammar as a standalone\n'
        'tree_sitter_gdscript module so graphify\'s ts_module config can load it."""\n'
        "from tree_sitter_language_pack import get_language\n\n\n"
        "def language():\n"
        '    """Return the GDScript tree_sitter.Language (graphify wraps it)."""\n'
        '    return get_language("gdscript")\n'
    )
    if shim.exists() and shim.read_text() == body:
        print(f"shim already current: {shim}")
        return
    shim.write_text(body)
    print(f"wrote shim: {shim}")


def _patch_detect(detect_py: Path) -> None:
    src = detect_py.read_text()
    if "'.gd'" in src.split("CODE_EXTENSIONS")[1].split("}")[0]:
        print("detect.py: .gd already in CODE_EXTENSIONS")
        return
    anchor = "CODE_EXTENSIONS = {'.py',"
    if anchor not in src:
        raise SystemExit("detect.py: CODE_EXTENSIONS anchor not found — graphify layout changed")
    detect_py.write_text(src.replace(anchor, "CODE_EXTENSIONS = {'.gd', '.py',", 1))
    print("detect.py: added '.gd' to CODE_EXTENSIONS")


_CONFIG_BLOCK = '''_GDSCRIPT_CONFIG = LanguageConfig(
    ts_module="tree_sitter_gdscript",
    ts_language_fn="language",
    class_types=frozenset({"class_definition"}),
    function_types=frozenset({"function_definition", "constructor_definition"}),
    import_types=frozenset(),
    call_types=frozenset({"call", "attribute_call"}),
    call_function_field="",
    name_field="name",
    name_fallback_child_types=("name", "identifier"),
    body_field="body",
    body_fallback_child_types=("body",),
    function_boundary_types=frozenset(
        {"function_definition", "constructor_definition", "class_definition"}
    ),
)


def extract_gdscript(path: Path) -> dict:
    """Extract classes, functions, and calls from a .gd (GDScript) file."""
    return _extract_generic(path, _GDSCRIPT_CONFIG)


'''

_CALL_BRANCH = '''            elif config.ts_module == "tree_sitter_gdscript":
                # GDScript: callee is the first identifier child (positional, no
                # named field) for both `call` and `attribute_call`.
                _gd_first = node.children[0] if node.children else None
                if _gd_first is not None and _gd_first.type == "identifier":
                    callee_name = _read_text(_gd_first, source)
'''


def _patch_extract(extract_py: Path) -> None:
    src = extract_py.read_text()

    # 1. Config + wrapper, inserted before extract_lua.
    if "_GDSCRIPT_CONFIG" not in src:
        anchor = "def extract_lua(path: Path) -> dict:"
        if anchor not in src:
            raise SystemExit("extract.py: extract_lua anchor not found")
        src = src.replace(anchor, _CONFIG_BLOCK + anchor, 1)
        print("extract.py: added _GDSCRIPT_CONFIG + extract_gdscript")
    else:
        print("extract.py: _GDSCRIPT_CONFIG already present")

    # 2. Dispatch entry.
    if '".gd": extract_gdscript' not in src:
        anchor = '    ".lua": extract_lua,\n'
        if anchor not in src:
            raise SystemExit("extract.py: _DISPATCH lua anchor not found")
        src = src.replace(anchor, anchor + '    ".gd": extract_gdscript,\n', 1)
        print("extract.py: registered .gd in _DISPATCH")
    else:
        print("extract.py: .gd already in _DISPATCH")

    # 3. Language-wrap fix (accept a provider that already returns a Language).
    if "_raw_lang = lang_fn()" not in src:
        anchor = "        language = Language(lang_fn())\n"
        if anchor not in src:
            raise SystemExit("extract.py: Language(lang_fn()) anchor not found")
        replacement = (
            "        _raw_lang = lang_fn()\n"
            "        language = _raw_lang if isinstance(_raw_lang, Language) "
            "else Language(_raw_lang)\n"
        )
        src = src.replace(anchor, replacement, 1)
        print("extract.py: made Language() robust to Language-returning providers")
    else:
        print("extract.py: Language-wrap fix already present")

    # 4. Positional-callee branch in the generic call handler.
    if "# GDScript: callee is the first identifier child" not in src:
        anchor = (
            "            else:\n"
            "                # Generic: get callee from call_function_field\n"
        )
        if anchor not in src:
            raise SystemExit("extract.py: generic call-handler anchor not found")
        src = src.replace(anchor, _CALL_BRANCH + anchor, 1)
        print("extract.py: added GDScript positional-callee branch")
    else:
        print("extract.py: GDScript call branch already present")

    extract_py.write_text(src)


def main() -> None:
    import graphify

    gdir = Path(graphify.__file__).parent
    site_dir = gdir.parent
    print(f"graphify: {gdir}")
    _ensure_language_pack()
    _write_shim(site_dir)
    _patch_detect(gdir / "detect.py")
    _patch_extract(gdir / "extract.py")
    print(
        "\nDone. Verify with:\n"
        "  python -c \"from graphify.extract import _DISPATCH; print('.gd' in _DISPATCH)\""
    )


if __name__ == "__main__":
    main()
