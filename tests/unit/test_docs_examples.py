"""Pin the examples and tables in the docs and skills to the live surface (#859).

The docs are part of the product surface, but the existing guards only pinned
counts and generated rows. These tests catch the drift a reader notices:
example calls with parameters the tool does not accept, incomplete error /
prompt / precondition tables, stale example-project counts, and an unpublished
walkthrough or cookbook.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from mcp_server.models.envelope import ErrorCode
from mcp_server.server import create_server, register_tool_transform
from mcp_server.toolset_protocol import SERVER_INSTRUCTIONS
from tests.helpers import list_all_tools

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "docs" / "site"
SKILLS = REPO_ROOT / "skills"

# ``godot_tool(param=value)`` — the parameter names are what the schema checks.
_CALL_RE = re.compile(r"\b(godot_[a-z0-9_]+)\s*\(([^()]*)\)", re.S)
_KWARG_RE = re.compile(r"(?:^|,)\s*([a-z_][a-z0-9_]*)\s*=")

# Project-defined tools are registered at runtime from ``## @mcp_tool``
# functions, so the static registry cannot know their names.
_GENERATED_PREFIX = "godot_project_"


def _tool_schemas() -> dict[str, dict[str, Any]]:
    server = create_server()
    asyncio.run(register_tool_transform(server))
    tools = asyncio.run(list_all_tools(server))
    out: dict[str, dict[str, Any]] = {}
    for tool in tools:
        schema = tool.parameters or {}
        out[tool.name] = {
            "properties": schema.get("properties") or {},
            "required": schema.get("required") or [],
        }
    return out


def _doc_sources() -> list[Path]:
    sources = [REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]
    sources.extend(REPO_ROOT.glob("docs/**/*.md"))
    sources.extend(SKILLS.rglob("*.md"))
    return [
        path
        for path in sources
        if path.is_file()
        and "node_modules" not in path.parts
        and "dist" not in path.parts
        and path.name != "changelog.md"
    ]


def _bad_calls(paths: list[Path]) -> list[str]:
    schemas = _tool_schemas()
    bad: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in _CALL_RE.finditer(text):
            name, args = match.group(1), match.group(2)
            if name not in schemas:
                # Generated project tools are expected to be absent statically.
                if name.startswith(_GENERATED_PREFIX):
                    continue
                bad.append(f"{path.relative_to(REPO_ROOT)}: unknown tool {name}()")
                continue
            allowed = set((schemas[name]["properties"] or {}).keys())
            for kw in _KWARG_RE.findall(args):
                if kw not in allowed:
                    bad.append(
                        f"{path.relative_to(REPO_ROOT)}: {name}({kw}=…) "
                        f"is not a parameter (valid: {sorted(allowed)})"
                    )
    return bad


def test_documented_tool_calls_use_live_parameter_names() -> None:
    """Examples must not teach a parameter the tool rejects at call time."""
    bad = _bad_calls(_doc_sources())
    assert not bad, "docs teach unknown tool parameters:\n" + "\n".join(bad)


def test_skill_tool_calls_use_live_parameter_names() -> None:
    """The same guard for the shipped skills and their reference guides."""
    bad = _bad_calls(sorted(SKILLS.rglob("*.md")))
    assert not bad, "skills teach unknown tool parameters:\n" + "\n".join(bad)


def test_error_code_tables_cover_the_enum() -> None:
    """Both architecture pages must name every ``ErrorCode`` member."""
    for rel in ("docs/architecture.md", "docs/site/architecture/envelope.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        missing = [code.value for code in ErrorCode if code.value not in text]
        assert not missing, f"{rel} omits error codes: {missing}"


def test_prompt_lists_cover_the_registry() -> None:
    """Docs and server instructions must name every registered prompt."""
    server = create_server()
    prompt_names = {p.name for p in asyncio.run(server.local_provider.list_prompts())}
    for label, text in {
        "docs/architecture.md": (REPO_ROOT / "docs/architecture.md").read_text(
            encoding="utf-8"
        ),
        "docs/site/reference-prompts.md": (
            SITE / "reference-prompts.md"
        ).read_text(encoding="utf-8"),
        "server instructions": SERVER_INSTRUCTIONS,
    }.items():
        missing = sorted(name for name in prompt_names if name not in text)
        assert not missing, f"{label} omits prompts: {missing}"


def test_precondition_tokens_are_documented() -> None:
    """The safety + error reference must cover every token the server emits."""
    tokens = {
        "active_scene",
        "confirm",
        "consent",
        "editor_ready",
        "bridge_connected",
        "runtime_probe",
        "play_session",
        "game_not_breaked",
        "godot_version",
        "godot_bin",
        "project_dir",
        "toolset",
        "human_approval",
    }
    combined = "\n".join(
        (REPO_ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            "docs/site/architecture/safety.md",
            "docs/site/reference-errors.md",
        )
    )
    missing = sorted(token for token in tokens if token not in combined)
    assert not missing, f"precondition tokens are undocumented: {missing}"


def test_examples_readme_counts_match_the_project() -> None:
    """The example README's test totals must match the files it describes."""
    text = (REPO_ROOT / "examples/README.md").read_text(encoding="utf-8")
    claim = re.search(r"(\d+) tests across (\d+) files", text)
    assert claim, "examples/README.md test claim not found"

    files = sorted((REPO_ROOT / "examples/survivors/tests/unit").glob("test_*.gd"))
    tests = sum(
        len(re.findall(r"^func test_", path.read_text(encoding="utf-8"), re.M))
        for path in files
    )
    assert int(claim.group(1)) == tests, (
        f"examples/README.md says {claim.group(1)} tests, actual is {tests}"
    )
    assert int(claim.group(2)) == len(files)


def test_addon_handler_count_matches_the_router() -> None:
    """The architecture page's handler count must match the preload table."""
    addon = REPO_ROOT / "docs/site/architecture/addon.md"
    text = addon.read_text(encoding="utf-8")
    match = re.search(r"\((\d+) domain\s+handler scripts", text)
    assert match, "addon.md domain-handler count not found"

    router = (REPO_ROOT / "godot/addons/godot_mcp/command_router.gd").read_text(
        encoding="utf-8"
    )
    preloads = len(re.findall(r'preload\("\./handlers/[a-z0-9_]+\.gd"\)', router))
    assert int(match.group(1)) == preloads, (
        f"addon.md says {match.group(1)} handler scripts, router preloads {preloads}"
    )


def test_walkthrough_and_cookbook_are_published() -> None:
    """The walkthrough and the example cookbook must be discoverable on the site."""
    walkthrough = SITE / "guides-walkthrough.md"
    cookbook = SITE / "guides-cookbook.md"
    assert walkthrough.is_file(), "docs/site/guides-walkthrough.md must ship"
    assert cookbook.is_file(), "docs/site/guides-cookbook.md must ship"

    config = (SITE / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    guides = (SITE / "guides.md").read_text(encoding="utf-8")
    for page in ("guides-walkthrough", "guides-cookbook"):
        assert f"/{page}" in config, f"{page} is not in the sidebar"
        assert f"{page}.md" in guides, f"guides.md does not link {page}"

    # ``llms-gen.mjs`` silently drops a source whose file is missing, so a
    # rename or typo would quietly remove the page from llms.txt and
    # llms-full.txt. Pin every listed source and the two new pages.
    llms_gen = (SITE / "llms-gen.mjs").read_text(encoding="utf-8")
    sections = llms_gen[
        llms_gen.index("const SECTIONS") : llms_gen.index("// Source path")
    ]
    sources = re.findall(r"'([^']+\.md)'", sections)
    missing_sources = [src for src in sources if not (SITE / src).is_file()]
    assert not missing_sources, (
        f"llms-gen.mjs lists missing pages: {missing_sources}"
    )
    for page in ("guides-walkthrough.md", "guides-cookbook.md"):
        assert page in sources, f"llms-gen.mjs SECTIONS omits {page}"

    cookbook_text = cookbook.read_text(encoding="utf-8")
    calls = set(_CALL_RE.findall(cookbook_text))
    assert len(calls) >= 20, (
        f"cookbook has {len(calls)} distinct tool calls; add worked examples"
    )
