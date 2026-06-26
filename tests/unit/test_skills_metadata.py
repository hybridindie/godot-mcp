"""Validation for the bundled Claude skills under ``skills/``.

Skills are client-side ``SKILL.md`` files that Claude auto-triggers on a
description match. They are not Python, but they are part of the product surface,
so we pin the things that silently rot: valid frontmatter, a name that matches
its directory, a usefully long trigger description, and — since every workflow on
this server starts with toolset gating — a reminder to enable a toolset.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest

from mcp_server.server import create_server

# Tool-call-shaped references in skill bodies, e.g. ``godot_runtime_play_scene(``.
# The trailing ``(`` avoids matching plugin/path tokens like ``addons/godot_mcp/``.
_TOOL_CALL_RE = re.compile(r"godot_[a-z0-9_]+(?=\()")

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# The skills we ship. Keep in lockstep with the directories under skills/.
EXPECTED_SKILLS = {
    "godot-mcp-getting-started",
    "godot-mcp-build-a-scene",
    "godot-mcp-playtest-and-debug",
}


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the leading ``---`` YAML-ish frontmatter block (flat key: value)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip().splitlines()
    out: dict[str, str] = {}
    for line in block:
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def test_expected_skills_present() -> None:
    """Every shipped skill directory exists with a SKILL.md."""
    assert SKILLS_DIR.is_dir(), "skills/ directory must exist"
    found = {p.name for p in _skill_dirs()}
    assert EXPECTED_SKILLS <= found, f"Missing skills: {EXPECTED_SKILLS - found}"
    for name in EXPECTED_SKILLS:
        assert (SKILLS_DIR / name / "SKILL.md").is_file(), f"{name}/SKILL.md missing"


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_skill_frontmatter_and_body(skill_name: str) -> None:
    """Each SKILL.md has valid frontmatter and teaches toolset gating."""
    text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)

    assert fm.get("name") == skill_name, f"frontmatter name must equal dir '{skill_name}'"
    description = fm.get("description", "")
    assert len(description) >= 40, "description must be descriptive enough to trigger on"
    assert "godot" in description.lower(), "description should mention Godot for relevance"

    body = text[text.find("\n---", 3) + 4 :]
    assert body.strip(), "SKILL.md must have a body after the frontmatter"
    # Every workflow on this server begins with enabling the right toolset.
    assert "godot_enable_toolset" in body, "skill body must show the toolset-gating step"


def test_skill_tool_references_exist() -> None:
    """Every godot_*() tool call shown in a skill resolves to a real tool.

    Guards against teaching the model tool names that don't exist (e.g. a renamed
    or imagined tool), which would silently fail at call time.
    """
    server: Any = create_server()
    tool_names = {t.name for t in asyncio.run(server._list_tools())}
    unknown: dict[str, set[str]] = {}
    for skill in _skill_dirs():
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        refs = set(_TOOL_CALL_RE.findall(text))
        missing = {r for r in refs if r not in tool_names}
        if missing:
            unknown[skill.name] = missing
    assert not unknown, f"Skills reference unknown tools: {unknown}"
