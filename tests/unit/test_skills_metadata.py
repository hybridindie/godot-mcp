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

from mcp_server import __version__
from mcp_server.server import create_server, register_tool_transform
from tests.helpers import list_all_tools

# Tool-call-shaped references in skill bodies, e.g. ``godot_runtime_play_scene(``.
# The trailing ``(`` avoids matching plugin/path tokens like ``addons/godot_mcp/``.
_TOOL_CALL_RE = re.compile(r"godot_[a-z0-9_]+(?=\()")

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# The skills we ship. Keep in lockstep with the directories under skills/.
EXPECTED_SKILLS = {
    "godot-getting-started",
    "godot-playtest-and-debug",
    "godot-expert",
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


# Skills that are engine knowledge, not tool workflows — exempt from the
# toolset-gating assertion (they teach Godot rules, not MCP tool calls).
NON_WORKFLOW_SKILLS = {"godot-expert"}


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
    # Every workflow skill begins with enabling the right toolset. Engine
    # knowledge skills (godot-expert) teach Godot rules, not tool calls.
    if skill_name not in NON_WORKFLOW_SKILLS:
        assert "godot_enable_toolset" in body, "skill body must show the toolset-gating step"


def test_skill_tool_references_exist() -> None:
    """Every godot_*() tool call shown in a skill resolves to a real tool.

    Guards against teaching the model tool names that don't exist (e.g. a renamed
    or imagined tool), which would silently fail at call time. Scans every
    markdown file under a skill (SKILL.md **and** references/) so a reference
    guide can't teach a phantom tool either.
    """
    server: Any = create_server()
    asyncio.run(register_tool_transform(server))
    tool_names = {t.name for t in asyncio.run(list_all_tools(server))}
    unknown: dict[str, set[str]] = {}
    for skill in _skill_dirs():
        for md in sorted(skill.rglob("*.md")):
            text = md.read_text(encoding="utf-8")
            refs = set(_TOOL_CALL_RE.findall(text))
            missing = {r for r in refs if r not in tool_names}
            if missing:
                unknown[f"{skill.name}/{md.relative_to(skill)}"] = missing
    assert not unknown, f"Skills reference unknown tools: {unknown}"


def test_every_reference_guide_is_linked() -> None:
    """Every reference file under a skill is linked from its SKILL.md — an
    unlinked guide is one the agent is told to read on demand but can never
    find, so it may as well not exist. Guards the authoring references added
    for #613 from drifting out of the index."""
    for skill in _skill_dirs():
        refs_dir = skill / "references"
        if not refs_dir.is_dir():
            continue
        skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
        unlinked = [
            f"references/{p.name}"
            for p in sorted(refs_dir.glob("*.md"))
            if p.name not in skill_text
        ]
        assert not unlinked, f"{skill.name}/SKILL.md does not link: {unlinked}"


# -- Drift guards (issue #381): skills stay in lockstep with the live surface --


def _body(skill_name: str) -> str:
    text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    return text[text.find("\n---", 3) + 4 :]


async def _toolsets() -> set[str]:
    from mcp_server.toolsets import TOOLSETS

    return set(TOOLSETS)


async def _prompt_names() -> set[str]:
    server: Any = create_server()
    names = {p.name for p in await server.local_provider.list_prompts()}
    return names


def test_getting_started_map_covers_every_toolset() -> None:
    """The quick-map names every gated toolset — a stale map teaches the agent
    to hunt for tools that were renamed or added since the skill was written."""
    body = _body("godot-getting-started")
    for toolset in sorted(asyncio.run(_toolsets())):
        assert toolset in body, (
            f"getting-started quick-map is missing the '{toolset}' toolset"
        )


def test_skill_prompt_lists_cover_registered_prompts() -> None:
    """Every registered MCP prompt is named in a workflow skill — agents reach
    for the canned recipes; a prompt missing from the skills is one they never
    discover."""
    combined = _body("godot-getting-started") + _body("godot-playtest-and-debug")
    prompts = asyncio.run(_prompt_names())
    missing = {p for p in prompts if p not in combined}
    assert not missing, f"Skills never mention these registered prompts: {missing}"


def test_getting_started_states_current_version_and_check() -> None:
    """The skill tells the agent which version this surface documents and how to
    verify the server it talks to matches (health_check → version). Both the
    skill body and the skills README name the version — a release bump must
    update both, so this pins both (the README previously drifted)."""
    body = _body("godot-getting-started")
    assert __version__ in body, (
        f"getting-started must name the current server version {__version__}"
    )
    assert "godot_health_check(" in body, (
        "getting-started must show the version check via godot_health_check()"
    )
    readme = (SKILLS_DIR / "README.md").read_text(encoding="utf-8")
    assert __version__ in readme, (
        f"skills/README.md must name the current version {__version__}"
    )


def test_skills_do_not_hardcode_stale_tool_counts() -> None:
    """The tool/category counts rot the moment a tool is added, and no test can
    pin a *number* to the surface without the skill becoming a mirror of the
    registry. The skills instead defer to the live inventory
    (``godot_get_server_info`` / ``godot_list_toolsets``). Bar the old
    hardcoded phrasings so a future edit can't silently reintroduce them."""
    stale = [
        "193 tools",
        "29 categories",
        "28 gated toolsets",
        "175 cmd",
        "175 `cmd",
    ]
    for name in (*EXPECTED_SKILLS, "README"):
        path = SKILLS_DIR / name / "SKILL.md" if name != "README" else SKILLS_DIR / "README.md"
        text = path.read_text(encoding="utf-8")
        for phrase in stale:
            assert phrase not in text, (
                f"{path.relative_to(SKILLS_DIR.parent)} hardcodes a stale count "
                f"('{phrase}'); defer to the live inventory instead"
            )


def test_getting_started_teaches_the_resource_surface() -> None:
    """The server exposes read-only ``godot://`` context resources plus the
    ``godot_read_resource`` fallback tool (#11). Getting-started must teach both
    — a client that never discovers resources loses the cheap read path, and a
    client without resource support has no way to reach them at all."""
    body = _body("godot-getting-started")
    assert "godot://" in body, "getting-started must mention godot:// resources"
    assert "godot_read_resource(" in body, (
        "getting-started must show the resources-as-tools fallback godot_read_resource()"
    )
    # Every context URI the server exposes must be named in the skill.
    for uri in (
        "godot://project/info",
        "godot://scene/current",
        "godot://scene/tree",
        "godot://node/selected",
    ):
        assert uri in body, f"resources section must name the real URI '{uri}'"


def test_playtest_skill_names_debugger_tools() -> None:
    """The debugger recipe names the real breakpoint/stepping tools instead of
    a vague 'set a breakpoint'."""
    body = _body("godot-playtest-and-debug")
    for tool in (
        "godot_debugger_set_breakpoint(",
        "godot_debugger_force_break(",
        "godot_debugger_get_stack_frames(",
    ):
        assert tool in body, f"playtest-and-debug must show {tool}"


def test_expert_skill_covers_4_8_gdscript_changes() -> None:
    """#588: the expert skill records the two Godot 4.8 GDScript behavior changes
    so an agent targeting/patching a 4.8 project does the right thing — a bare
    string literal is now a standalone-expression warning (no more ad-hoc
    multiline comments), and a class can no longer inherit from its own inner
    class (cyclic inheritance). Both were called out in the 4.8 readiness audit.
    """
    body = _body("godot-expert")
    assert "4.8" in body, "godot-expert must note the Godot 4.8 GDScript changes"
    assert "inner class" in body.lower(), (
        "godot-expert must document the no-self-inner-class-inheritance change"
    )
    assert "comment" in body.lower(), (
        "godot-expert must document that bare strings are no longer comments"
    )


def test_expert_skill_has_no_raw_bridge_workflow() -> None:
    """§8 predates the MCP server: the /tmp/bridge_cmd.py raw-bridge workflow is
    obsolete — agents call godot_* tools, never the bridge files."""
    body = _body("godot-expert")
    assert "bridge_cmd.py" not in body, (
        "godot-expert still teaches the obsolete raw-bridge bridge_cmd.py workflow"
    )


def test_expert_skill_script_save_claim_is_accurate() -> None:
    """The handler writes scripts to disk immediately (FileAccess in the
    UndoRedo do-method); only unsaved *scene edits* need save_scene. The old
    'write_script does not flush to disk' claim was wrong — and it had resurfaced
    in references/scene-authoring.md, which the earlier body-only guard missed.
    Now scans every markdown file under the skill."""
    text = "\n".join(
        md.read_text(encoding="utf-8") for md in sorted((SKILLS_DIR / "godot-expert").rglob("*.md"))
    )
    assert "does NOT flush to disk" not in text, (
        "godot-expert still claims write_script does not flush to disk"
    )
    assert "cmd_write_script" not in text, (
        "godot-expert references the raw cmd_write_script bridge command"
    )
    # The corrected rule must still teach that scene edits need an explicit save.
    assert "godot_scene_edit_save_scene(" in text or "save_scene" in text, (
        "godot-expert must teach save_scene for scene edits"
    )
