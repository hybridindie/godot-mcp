"""Contract: the CalVer version is consistent across every copy (issue #656).

The version is hand-edited in several files (pyproject, `__init__`, `plugin.cfg`,
README badge, skills). A release that updates one and not the others ships a
mismatched claim; this pins them to a single value.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# file -> regex capturing the version.
_COPIES: dict[str, str] = {
    "pyproject.toml": r'^version = "([^"]+)"',
    "mcp_server/__init__.py": r'__version__ = "([^"]+)"',
    "godot/addons/godot_mcp/plugin.cfg": r'version="([^"]+)"',
    "README.md": r"version-([0-9][^-]*)-brightgreen",
    "skills/README.md": r"as of \*\*([0-9][^*]*)\*\*",
    "skills/godot-getting-started/SKILL.md": r"\*\*([0-9][^*]*)\*\* surface",
}


def test_every_version_copy_agrees() -> None:
    found: dict[str, str | None] = {}
    for rel, pattern in _COPIES.items():
        match = re.search(pattern, (_ROOT / rel).read_text(encoding="utf-8"), re.MULTILINE)
        found[rel] = match.group(1) if match else None
    missing = [k for k, v in found.items() if v is None]
    assert not missing, f"version not found in: {missing}"
    assert len(set(found.values())) == 1, f"version copies disagree: {found}"
