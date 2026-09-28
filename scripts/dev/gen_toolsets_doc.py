"""Regenerate ``docs/site/reference-toolsets.md`` from the live tool registry.

The page is generated so the table cannot silently drift from the code (the
2026.09.23/28 releases bumped only the count prose while the table lost 9
tools). Run after any surface change:

    GODOT_MCP_DEFAULT_TOOLSETS=all uv run python scripts/dev/gen_toolsets_doc.py
    cd docs/site && npm run build && node check-links.mjs

The tool descriptions (the text after ``—`` per section) are NOT generated:
they are hand-written prose kept from the previous table. This script rewrites
the counts + rows and preserves each existing section header verbatim, so a
re-run only touches what the registry changed.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "docs" / "site"
TARGET = SITE / "reference-toolsets.md"


async def _collect() -> list[dict[str, str]]:
    from mcp_server.server import create_server
    from mcp_server.transforms import godot_tool_name

    mcp = create_server()
    tools = await mcp.local_provider.list_tools()
    rows: list[dict[str, str]] = []
    for t in tools:
        safety = (t.meta or {}).get("safety_class") if isinstance(t.meta, dict) else None
        cat_tags = sorted(x for x in (t.tags or []) if x != "core")
        cat = cat_tags[0] if cat_tags else "core"
        rows.append(
            {
                "name": godot_tool_name(t.name, t.tags),
                "cat": cat,
                "safety": safety or "read_only",
            }
        )
    return rows


def main() -> None:
    rows = asyncio.run(_collect())
    by_cat: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_cat.setdefault(r["cat"], []).append(r)
    for tools in by_cat.values():
        tools.sort(key=lambda r: r["name"])

    doc = TARGET.read_text()

    # Preserve the existing "## `<cat>` — <hand-written description>" headers.
    headers: dict[str, str] = {}
    for m in re.finditer(r"^## `(\w+)` — (.+)$", doc, re.M):
        headers[m.group(1)] = m.group(2)

    order = re.findall(r"^## `(\w+)`", doc, re.M)
    missing_cats = sorted(set(by_cat) - set(order))
    if missing_cats:
        raise SystemExit(
            f"new toolset(s) without a section in reference-toolsets.md: {missing_cats} — "
            "add a `## <cat> — <description>` header first, then re-run"
        )

    lines: list[str] = []
    total = len(rows)
    # (the intro count line is written by the frontmatter pass below — the body
    # starts at the first section)
    for cat in order:
        tools = by_cat.get(cat, [])
        lines.append(f"## `{cat}` — {headers.get(cat, cat)}")
        lines.append("")
        lines.append(f"{len(tools)} tools.")
        lines.append("")
        lines.append("| Tool | Class |")
        lines.append("|------|-------|")
        for t in tools:
            lines.append(f"| `{t['name']}` | {t['safety']} |")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"

    # Splice: replace everything from the first `## ` heading to EOF, keeping
    # the frontmatter + H1 + the intro count line (which the frontmatter pass
    # already refreshed — don't duplicate it in the body).
    first_h2 = doc.index("## `")
    front = doc[:first_h2]
    # refresh frontmatter `updated:` + the count line in the intro
    updated = f"updated: {date.today().isoformat()}"
    front = re.sub(r"^updated: .*$", updated, front, count=1, flags=re.M)
    front = re.sub(
        r"^\d+ tools across \d+ categories\.",
        f"{total} tools across {len(order)} categories.",
        front,
        count=1,
        flags=re.M,
    )
    front = re.sub(
        r'description: "Every tool in the [0-9.]+ surface',
        f'description: "Every tool in the {total}-tool surface',
        front,
        count=1,
    )
    TARGET.write_text(front + body)
    print(f"regenerated {TARGET.name}: {total} tools across {len(order)} toolsets")


if __name__ == "__main__":
    main()