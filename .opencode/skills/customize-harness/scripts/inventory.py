#!/usr/bin/env python3
"""Compact inventory for customize-harness; no file bodies in the output."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "dist", "build", "target",
    "__pycache__", ".next", ".nuxt", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", "graphify-out", "coverage", "htmlcov",
}

# Extension -> OpenCode built-in LSP server id.
EXT_TO_SERVER = {
    ".py": "pyright", ".pyi": "pyright",
    ".ts": "typescript", ".tsx": "typescript", ".js": "typescript",
    ".jsx": "typescript", ".mjs": "typescript", ".cjs": "typescript",
    ".rs": "rust", ".go": "gopls",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".ksh": "bash",
    ".yml": "yaml-ls", ".yaml": "yaml-ls",
    ".lua": "lua-ls", ".cs": "csharp", ".java": "jdtls", ".rb": "ruby-lsp",
    ".tf": "terraform", ".tfvars": "terraform", ".nix": "nixd",
}

# Extensions with no OpenCode built-in server; reported so the plan can say so.
# A custom server entry declaring the extension satisfies it instead.
EXT_NO_SERVER = {".gd": "godot", ".vue": "vue", ".svelte": "svelte", ".astro": "astro"}
LANG_EXT = {language: ext for ext, language in EXT_NO_SERVER.items()}

# Server id -> command that must resolve on PATH for it to start.
SERVER_BINARY = {
    "pyright": "pyright-langserver",
    "typescript": "typescript-language-server",
    "rust": "rust-analyzer",
    "gopls": "gopls",
    "bash": "bash-language-server",
    "yaml-ls": "yaml-language-server",
    "lua-ls": "lua-language-server",
    "csharp": "dotnet",
    "jdtls": "java",
    "ruby-lsp": "ruby-lsp",
    "terraform": "terraform-ls",
    "nixd": "nixd",
    "godot": "godot-lsp",
}

# Servers OpenCode fetches itself on first use, so a missing binary is not fatal.
AUTO_INSTALL = {"bash", "yaml-ls"}

MAX_FILES = 20000


def read_json(path: Path):
    """The parsed JSON object, or None when it is missing, unreadable or not an object."""
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def opencode_configs(root: Path) -> list[Path]:
    """OpenCode merges a root opencode.json with .opencode/opencode.json."""
    return [p for p in (root / "opencode.json", root / ".opencode" / "opencode.json") if p.is_file()]


def scan_languages(root: Path) -> tuple[dict[str, int], dict[str, int], int, bool]:
    """Count source files per LSP server and per server-less language."""
    servers: dict[str, int] = {}
    unsupported: dict[str, int] = {}
    scanned = 0
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if scanned >= MAX_FILES:
                return servers, unsupported, scanned, True
            scanned += 1
            ext = Path(name).suffix.lower()
            if ext in EXT_TO_SERVER:
                server = EXT_TO_SERVER[ext]
                servers[server] = servers.get(server, 0) + 1
            elif ext in EXT_NO_SERVER:
                language = EXT_NO_SERVER[ext]
                unsupported[language] = unsupported.get(language, 0) + 1
    return servers, unsupported, scanned, False


def lsp_report(root: Path) -> dict:
    configs = opencode_configs(root)
    parsed: dict[Path, dict] = {}
    invalid = False
    for config in configs:
        data = read_json(config)
        if data is None:
            invalid = True
        else:
            parsed[config] = data

    lsp_entries = [d["lsp"] for d in parsed.values() if "lsp" in d]
    combined: dict = {}
    for entry in lsp_entries:
        if isinstance(entry, dict):
            combined.update(entry)

    if not configs:
        current: object = "<no-config>"
    elif not parsed:
        current = "<invalid>"
    elif not lsp_entries:
        current = "<absent>"
    else:
        current = {
            "servers_set": sorted(k for k, v in combined.items()
                                  if not (isinstance(v, dict) and v.get("disabled"))),
            "disabled": sorted(k for k, v in combined.items()
                               if isinstance(v, dict) and v.get("disabled")),
        }
    servers, unsupported, scanned, truncated = scan_languages(root)

    # A custom server entry declaring one of the server-less extensions covers
    # that language, so it is not a gap after all (e.g. the godot bridge).
    custom_exts: dict[str, str] = {}
    for name, item in combined.items():
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        for ext in item.get("extensions") or []:
            custom_exts[str(ext).lower()] = name
    for language, count in list(unsupported.items()):
        server = custom_exts.get(LANG_EXT[language])
        if server:
            servers[server] = servers.get(server, 0) + count
            del unsupported[language]

    missing, auto_installable = [], []
    for server in sorted(servers):
        binary = SERVER_BINARY.get(server)
        if binary and shutil.which(binary) is None:
            (auto_installable if server in AUTO_INSTALL else missing).append(server)

    # A dead `lsp` key in Claude settings is silently ignored; flag it.
    claude = read_json(root / ".claude" / "settings.json")
    return {
        "config_path": str(configs[0].relative_to(root)) if configs else ".opencode/opencode.json",
        "config_present": bool(configs),
        "config_parse_error": invalid,
        "current": current,
        "detected_servers": dict(sorted(servers.items())),
        "no_builtin_server": dict(sorted(unsupported.items())),
        "binaries_missing": missing,
        "auto_install_on_first_use": auto_installable,
        "files_scanned": scanned,
        "scan_truncated": truncated,
        "claude_settings_has_lsp_key": bool(claude and "lsp" in claude),
    }


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
    package = read_json(root / "package.json") or {}
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
        "lsp": lsp_report(root),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
