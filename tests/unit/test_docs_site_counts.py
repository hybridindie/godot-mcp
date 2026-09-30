"""Pin the tool/category counts stated in the docs site to the live registry (#612).

The site states the surface size in many places: the tagline, the VitePress
config description and footer, the ``llms-gen.mjs`` summary, and several
concept/architecture pages ("193 tools", "29 gated toolsets", "the 193-tool
surface"). Those numbers drift silently on every tool addition — the skills
had the same problem and #611 fixed it there. This test pins them so a surface
change that leaves the prose stale fails the suite.

Scope: hand-written *current-state* prose under ``docs/site`` (plus the config
and generator). Excluded:

- ``changelog.md`` — historical entries legitimately name old counts (e.g.
  "was 192") and must not be rewritten.
- ``reference-toolsets.md`` — generated from the registry; its per-toolset
  "N tools." lines are counts of *one* category, not the total, and the
  generator owns them. (Its intro total line is still pinned here.)
- ``node_modules`` / ``dist`` — not source.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from mcp_server.server import create_server, register_tool_transform
from mcp_server.toolsets import TOOLSETS
from tests.helpers import list_all_tools

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "docs" / "site"

# Files whose counts are historical or generated, not current-state prose.
_EXCLUDE_FILES = {"changelog.md", "reference-toolsets.md"}

# (pattern, which live count(s) the number may equal). Two distinct surfaces are
# stated legitimately: the TOTAL surface (all tools / all categories) and the
# DEFAULT surface (core + inspection only). "N tools" must be one of those; a
# number that is neither is drift.
_PATTERNS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    # "N gated toolsets" is the site's loose phrasing for the total toolset
    # count (they are all gated by default), so it pins to `toolsets`.
    (re.compile(r"\b(\d+)\s+gated toolsets\b"), ("toolsets",)),
    (re.compile(r"\b(\d+)\s+toolsets\b"), ("toolsets",)),
    (re.compile(r"\b(\d+)\s+categor(?:y|ies)\b"), ("toolsets",)),
    (re.compile(r"\b(\d+)-tool\b"), ("tools", "default_tools")),
    (re.compile(r"\b(\d+)\s+tools\b"), ("tools", "default_tools")),
]

# A generated per-section line, e.g. "9 tools." on its own line — a count of one
# category, not the total. Only appears in the generated page, but skip it
# anywhere so a future hand-written section can't trip the guard.
_SECTION_COUNT_LINE = re.compile(r"^\d+ tools\.$")


def _live_counts() -> dict[str, int]:
    server = create_server()
    asyncio.run(register_tool_transform(server))
    tools = asyncio.run(list_all_tools(server))
    default = sum(
        1 for t in tools if {"core", "inspection"} & set(t.tags or [])
    )
    return {
        "tools": len(tools),
        "toolsets": len(TOOLSETS) + 1,  # +1: always-on core
        "default_tools": default,  # the core + inspection surface (23)
        "gated_toolsets": len(TOOLSETS) - 1,  # all but core and inspection
    }


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(SITE.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {"node_modules", "dist"} for part in path.parts):
            continue
        if path.name in _EXCLUDE_FILES:
            continue
        if path.suffix in {".md", ".mjs", ".mts", ".ts"}:
            files.append(path)
    return files


def test_docs_site_counts_match_the_live_registry() -> None:
    live = _live_counts()
    stale: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _SECTION_COUNT_LINE.match(line.strip()):
                continue
            # Ignore historical parentheticals ("was 192") — a stated *old* count.
            if re.search(r"\bwas\s+\d+", line):
                continue
            for pattern, keys in _PATTERNS:
                for match in pattern.finditer(line):
                    stated = int(match.group(1))
                    allowed = {live[k] for k in keys}
                    if stated not in allowed:
                        rel = path.relative_to(REPO_ROOT)
                        stale.append(
                            f"{rel}:{lineno}: states {stated} "
                            f"(expected one of {sorted(allowed)}): {line.strip()[:120]}"
                        )
    assert not stale, "docs-site counts drifted from the registry:\n" + "\n".join(stale)


def test_reference_toolsets_intro_total_matches_registry() -> None:
    """The generated page's intro total is pinned even though the file is
    excluded from the broad scan (its per-section counts are a different thing).
    Catches a registry change that skipped `scripts/dev/gen_toolsets_doc.py`."""
    live = _live_counts()
    text = (SITE / "reference-toolsets.md").read_text(encoding="utf-8")
    m = re.search(r"^(\d+) tools across (\d+) categories\.", text, re.M)
    assert m, "reference-toolsets.md intro line not found"
    assert int(m.group(1)) == live["tools"], (
        f"reference-toolsets.md says {m.group(1)} tools, registry has {live['tools']} "
        "— re-run scripts/dev/gen_toolsets_doc.py"
    )
    assert int(m.group(2)) == live["toolsets"], (
        f"reference-toolsets.md says {m.group(2)} categories, registry has {live['toolsets']}"
    )
