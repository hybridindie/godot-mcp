#!/usr/bin/env python3
"""Compact inventory for customize-harness; no file bodies in the output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    readme = root / "README.md"
    first_line = ""
    if readme.is_file():
        for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                first_line = line.lstrip("# ").strip()
                break
    package = read_json(root / "package.json")
    pyproject = root / "pyproject.toml"
    pyproject_text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    name_match = re.search(r'^name\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    workflow_sections: dict[str, list[str]] = {}
    wf = root / "my-workflows.md"
    if wf.is_file():
        section = ""
        for line in wf.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                section = line.strip("# ").strip()
                workflow_sections.setdefault(section, [])
            elif section and line.strip():
                workflow_sections[section].append(line.strip())
    workflows = [
        {"section": name, "filled": any("<" not in line and "placeholder" not in line.lower() for line in lines)}
        for name, lines in workflow_sections.items()
    ]
    counts = {}
    for key, pattern in {
        "rules": ".claude/rules/**/*.md",
        "agents": ".claude/agents/*.md",
        "commands": ".claude/commands/*.md",
        "claude_skills": ".claude/skills/*/SKILL.md",
        "opencode_skills": ".opencode/skills/*/SKILL.md",
    }.items():
        counts[key] = len(list(root.glob(pattern)))
    agents = root / "AGENTS.md"
    rows = 0
    if agents.is_file():
        rows = len(re.findall(r"^\|\s*`\.claude/rules/", agents.read_text(encoding="utf-8"), re.MULTILINE))
    print(json.dumps({
        "project": {
            "readme": first_line,
            "package_name": package.get("name", ""),
            "package_description": package.get("description", ""),
            "pyproject_name": name_match.group(1) if name_match else "",
        },
        "counts": counts,
        "rule_index_rows": rows,
        "workflow_sections": workflows,
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
