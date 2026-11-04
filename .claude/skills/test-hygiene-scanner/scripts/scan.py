#!/usr/bin/env python3
"""Deterministic test-hygiene scan. The model only triages the hits."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CATEGORIES = {
    "hardcoded-dates": re.compile(r"20\d{2}-\d{2}-\d{2}|Date\.parse\(\"|grace_expires_at"),
    "asyncmock": re.compile(r"AsyncMock|__getitem__|__enter__"),
    "cross-tier-truncate": re.compile(r"autouse\s*=\s*True|\.delete\(\)\.neq|truncate_all_tables"),
    "envelope": re.compile(r"assert\s+[\"']detail[\"']|\[\s*[\"']detail[\"']\s*\]|error_data"),
    "singleton": re.compile(r"get_prompt_loader|get_async_supabase|mlflow"),
}

def is_test(path: Path) -> bool:
    name = path.name
    return (
        "/tests/" in path.as_posix()
        or name.endswith((".test.ts", ".test.tsx", ".test.py", ".spec.ts", ".spec.tsx"))
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["tests"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    roots = [Path(p) for p in args.paths]
    hits: list[dict[str, object]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not is_test(path) or path.stat().st_size > 1_000_000:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(lines, 1):
                for category, pattern in CATEGORIES.items():
                    if pattern.search(line):
                        hits.append({"category": category, "file": str(path), "line": lineno, "text": line.strip()})
    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        for hit in hits:
            print(f"{hit['category']}\t{hit['file']}:{hit['line']}\t{hit['text']}")
    print(f"scanned={sum(1 for _ in roots)} hits={len(hits)}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
