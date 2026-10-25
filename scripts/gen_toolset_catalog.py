#!/usr/bin/env python3
"""Regenerate the mechanical parts of ``docs/site/reference-toolsets.md`` (#828).

The site catalog duplicated all 201 tool rows from ``docs/tool-contracts.md`` by
hand: every tool addition meant two edits, and the counts could drift. This
script rewrites **only** the generated parts, in place:

- the intro's ``N tools across M categories.`` line,
- each toolset section's ``N tools.`` count and ``| Tool | Class |`` table.

Headings, curated descriptions, prose notes (e.g. the project-tools note) and
section order are preserved byte-for-byte.

Usage:
    python scripts/gen_toolset_catalog.py            # rewrite the doc
    python scripts/gen_toolset_catalog.py --check    # exit 1 on drift
    python scripts/gen_toolset_catalog.py --file X   # operate on a copy
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.categories import CORE_TAG
from mcp_server.server import create_server
from mcp_server.transforms import _original_handler_name, godot_tool_name

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOC = ROOT / "docs" / "site" / "reference-toolsets.md"

_HEADING = re.compile(r"^## `([a-z0-9_]+)` — ")
_COUNT = re.compile(r"^\d+ tools?\.$")
_INTRO = re.compile(r"\b\d+ tools across \d+ categories\.")
_TABLE_HEADER = "| Tool | Class |"
_TABLE_RULE = "|------|-------|"


def _registry() -> dict[str, list[tuple[str, str]]]:
    """Live tool surface grouped by gating category, alphabetically sorted."""
    server = create_server()
    tools = asyncio.run(server.local_provider.list_tools())
    groups: dict[str, list[tuple[str, str]]] = {}
    for tool in tools:
        name = godot_tool_name(_original_handler_name(tool), tool.tags)
        tags = set(tool.tags or ()) - {CORE_TAG}
        category = next(iter(tags), None) or CORE_TAG
        safety = str((tool.meta or {}).get("safety_class", "unclassified"))
        groups.setdefault(category, []).append((name, safety))
    return {category: sorted(rows) for category, rows in groups.items()}


def _rewrite_body(
    body: list[str], category: str, rows: list[tuple[str, str]]
) -> list[str]:
    """Replace the count line and table rows in one section, keeping the prose."""
    if not rows:
        raise SystemExit(f"error: section '{category}' has no tools in the registry")
    count_at = next((i for i, line in enumerate(body) if _COUNT.match(line)), None)
    header_at = next((i for i, line in enumerate(body) if line == _TABLE_HEADER), None)
    if count_at is None or header_at is None or header_at + 1 >= len(body):
        raise SystemExit(
            f"error: section '{category}' is missing its '{_COUNT.pattern}' line or table"
        )
    if body[header_at + 1] != _TABLE_RULE:
        raise SystemExit(f"error: section '{category}' table has an unexpected header rule")

    end = header_at + 2
    while end < len(body) and body[end].startswith("|"):
        end += 1

    table = [_TABLE_HEADER, _TABLE_RULE, *(f"| `{name}` | {safety} |" for name, safety in rows)]
    return [
        *body[:count_at],
        f"{len(rows)} tools.",
        *body[count_at + 1 : header_at],
        *table,
        *body[end:],
    ]


def render(text: str, groups: dict[str, list[tuple[str, str]]]) -> str:
    """The doc with its generated parts refreshed; everything else untouched."""
    total = sum(len(rows) for rows in groups.values())
    lines = text.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < len(lines):
        match = _HEADING.match(lines[i])
        if not match:
            intro = f"{total} tools across {len(groups)} categories."
            out.append(_INTRO.sub(intro, lines[i], count=1))
            i += 1
            continue

        category = match.group(1)
        seen.add(category)
        out.append(lines[i])
        i += 1
        body: list[str] = []
        while i < len(lines) and not _HEADING.match(lines[i]):
            body.append(lines[i])
            i += 1
        out.extend(_rewrite_body(body, category, groups.get(category, [])))

    missing = sorted(set(groups) - seen)
    if missing:
        raise SystemExit(
            "error: the registry has toolsets with no section: " + ", ".join(missing)
        )
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the doc is stale")
    parser.add_argument("--file", type=Path, default=DEFAULT_DOC, help="doc to update")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8")
    rendered = render(text, _registry())

    if rendered == text:
        print(f"{args.file} is up to date")
        return 0
    if args.check:
        diff = difflib.unified_diff(
            text.splitlines(), rendered.splitlines(), fromfile=str(args.file), tofile="generated"
        )
        print("\n".join(diff), file=sys.stderr)
        print(
            f"\n{args.file} is stale; run python scripts/gen_toolset_catalog.py",
            file=sys.stderr,
        )
        return 1

    args.file.write_text(rendered, encoding="utf-8")
    print(f"updated {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
