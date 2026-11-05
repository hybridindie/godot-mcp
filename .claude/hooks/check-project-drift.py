#!/usr/bin/env python3
"""Check that the rendered harness still describes the project it lives in.

This is a deterministic, low-context gate: it reads the small
`.claude/harness.json` manifest plus the files it names, and prints only drift.
It does not ask a model to judge prose. The template-source counterpart is
`templates/scripts/check-harness-sync.py`; this file validates a deployed project.

Checks:
  1. The manifest is present and valid, and its stacks/packs match the rule files.
  2. `AGENTS.md` indexes every rule exactly once, and every rule has read_when.
  3. The Commands and Skills sections match the directories on disk.
  4. The Claude/OpenCode mirrors have the same commands, skills, and agents.
  5. `CLAUDE.md` stays a thin import of `AGENTS.md` and `my-workflows.md`.
  6. The Python version in `AGENTS.md` and `pyproject.toml` matches the manifest.
  7. No rendered placeholder survived.
  8. The expected hooks and git hooks exist.

Exit 0 when clean, 1 when drift is found. Use --quiet in git hooks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# One marker rule per stack/pack: present when declared, absent otherwise.
STACK_MARKERS = {
    "python": "packaging.md",
    "mcp": "mcp-contract.md",
    "agent": "agent-system.md",
    "fastapi": "api-design.md",
    "frontend": "frontend/conventions.md",
    "godot": "godot.md",
    "godot-addon": "godot-addon.md",
    "rust": "rust.md",
}
PACK_MARKERS = {
    "production": "deploy-safety.md",
    "acd": "agentic-workflow.md",
}
LEGACY_PROFILES = {"web": ["fastapi", "frontend"]}

PLACEHOLDER = re.compile(r"\{\{[A-Z_][A-Z0-9_]*\}\}")

class Drift:
    def __init__(self, root: Path, quiet: bool = False) -> None:
        self.root = root
        self.quiet = quiet
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks = 0

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def check(self, ok: bool, message: str) -> bool:
        self.checks += 1
        if not ok:
            self.fail(message)
        return ok

    # ── Manifest, stacks and packs ────────────────────────────────────

    def manifest(self) -> dict | None:
        path = self.root / ".claude" / "harness.json"
        if not path.is_file():
            self.fail("DRIFT: .claude/harness.json is missing (re-run the bootstrap)")
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.fail(f"DRIFT: .claude/harness.json is not valid JSON: {exc}")
            return None
        if not isinstance(data, dict):
            self.fail("DRIFT: .claude/harness.json must contain an object")
            return None
        schema = data.get("schema")
        self.check(schema in (1, 2), f"DRIFT: unsupported harness.json schema {schema!r}")
        if schema == 1:  # single-profile harness from an older bootstrap
            profile = data.get("profile") or "python"
            data["stacks"] = LEGACY_PROFILES.get(profile, [profile])
            data.setdefault("packs", ["acd"] if profile == "agent" else [])
        for stack in data.get("stacks") or []:
            self.check(stack in STACK_MARKERS, f"DRIFT: unknown stack in harness.json: {stack!r}")
        for pack in data.get("packs") or []:
            self.check(pack in PACK_MARKERS, f"DRIFT: unknown pack in harness.json: {pack!r}")
        return data

    def stacks(self, manifest: dict) -> None:
        rules = self.root / ".claude" / "rules"
        for kind, markers, declared in (
            ("stack", STACK_MARKERS, set(manifest.get("stacks") or [])),
            ("pack", PACK_MARKERS, set(manifest.get("packs") or [])),
        ):
            for name, marker in sorted(markers.items()):
                present = (rules / marker).is_file()
                if name in declared:
                    if not present:  # tailored repos may cover a stack under their own rule name
                        self.warn(f"WARN: {kind} {name} has no .claude/rules/{marker}")
                elif present:
                    self.fail(
                        f"DRIFT: .claude/rules/{marker} belongs to {kind} {name}, which harness.json "
                        f"does not declare (add it to {kind}s or delete the rule)"
                    )

    # ── Rule index ─────────────────────────────────────────────────────

    def rule_index(self) -> None:
        agents = self.root / "AGENTS.md"
        if not self.check(agents.is_file(), "DRIFT: AGENTS.md is missing"):
            return
        text = agents.read_text(encoding="utf-8")
        rules_dir = self.root / ".claude" / "rules"
        actual = {
            p.relative_to(rules_dir).as_posix()
            for p in rules_dir.rglob("*.md")
            if not p.relative_to(rules_dir).as_posix().startswith("doctrine/")
        }
        indexed = set(
            re.findall(r"^\|\s*`\.claude/rules/([^`]+)`\s*\|", text, re.MULTILINE)
        )
        for missing in sorted(actual - indexed):
            self.fail(f"DRIFT: rule not indexed in AGENTS.md: .claude/rules/{missing}")
        for extra in sorted(indexed - actual):
            self.fail(f"DRIFT: AGENTS.md indexes a missing rule: .claude/rules/{extra}")
        for rel in sorted(actual):
            body = (rules_dir / rel).read_text(encoding="utf-8")
            frontmatter = re.match(r"^---\n(.*?)\n---", body, re.DOTALL)
            self.check(
                bool(frontmatter and "read_when:" in frontmatter.group(1)),
                f"DRIFT: rule has no read_when: .claude/rules/{rel}",
            )

    # ── Harness map lists ──────────────────────────────────────────────

    @staticmethod
    def section(text: str, heading: str) -> str:
        match = re.search(
            rf"^### {re.escape(heading)}\s*\n(.*?)(?=^### |^## |\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        return match.group(1) if match else ""

    def map_lists(self) -> None:
        agents = self.root / "AGENTS.md"
        if not agents.is_file():
            return
        text = agents.read_text(encoding="utf-8")

        command_files = {
            p.stem for p in (self.root / ".claude" / "commands").glob("*.md")
        }
        commands_text = self.section(text, "Commands")
        if not commands_text:
            self.warn("WARN: AGENTS.md has no ### Commands section; skipping command list check")
        else:
            listed_commands = set(re.findall(r"/([a-z0-9][a-z0-9-]*)", commands_text))
            for name in sorted(command_files - listed_commands):
                self.fail(f"DRIFT: command /{name} exists but is not listed in AGENTS.md")
            for name in sorted(listed_commands - command_files):
                self.fail(f"DRIFT: AGENTS.md lists /{name} but .claude/commands/{name}.md is missing")

        skill_dirs = {
            p.parent.name
            for p in (self.root / ".claude" / "skills").glob("*/SKILL.md")
        }
        skills_text = self.section(text, "Skills")
        if not skills_text:
            self.warn("WARN: AGENTS.md has no ### Skills section; skipping skill list check")
        else:
            listed_skills = set(re.findall(r"`([a-z0-9][a-z0-9-]*)`", skills_text))
            for name in sorted(skill_dirs - listed_skills):
                self.fail(f"DRIFT: skill {name} exists but is not listed in AGENTS.md")
            for name in sorted(listed_skills - skill_dirs):
                self.fail(f"DRIFT: AGENTS.md lists skill {name} but .claude/skills/{name}/SKILL.md is missing")

    # ── Mirrors ────────────────────────────────────────────────────────

    def mirrors(self) -> None:
        pairs = [("commands", "*.md", lambda p: p.stem), ("skills", "*/SKILL.md", lambda p: p.parent.name)]
        for folder, pattern, name in pairs:
            claude = self.root / ".claude" / folder
            opencode = self.root / ".opencode" / folder
            left = {name(p) for p in claude.glob(pattern)}
            right = {name(p) for p in opencode.glob(pattern)}
            for missing in sorted(left - right):
                self.fail(f"DRIFT: .opencode/{folder} is missing {missing}")
            for extra in sorted(right - left):
                self.fail(f"DRIFT: .opencode/{folder} has no Claude counterpart: {extra}")
        if (self.root / ".claude" / "agents").is_dir():
            left = {p.name for p in (self.root / ".claude" / "agents").glob("*.md")}
            right = {p.name for p in (self.root / ".opencode" / "agents").glob("*.md")}
            for missing in sorted(left - right):
                self.fail(f"DRIFT: .opencode/agents is missing {missing}")
            for extra in sorted(right - left):
                self.fail(f"DRIFT: .opencode/agents has no Claude counterpart: {extra}")

    # ── Context files ──────────────────────────────────────────────────

    def context_files(self) -> None:
        claude = self.root / "CLAUDE.md"
        if self.check(claude.is_file(), "DRIFT: CLAUDE.md is missing"):
            text = claude.read_text(encoding="utf-8")
            self.check("@AGENTS.md" in text, "DRIFT: CLAUDE.md must import @AGENTS.md")
            self.check(
                "@my-workflows.md" in text,
                "DRIFT: CLAUDE.md must import @my-workflows.md",
            )
            self.check(
                len(text.splitlines()) <= 60,
                "DRIFT: CLAUDE.md is no longer thin; move content to AGENTS.md",
            )
        workflows = self.root / "my-workflows.md"
        self.check(workflows.is_file(), "DRIFT: my-workflows.md is missing")

        config_path = self.root / ".opencode" / "opencode.json"
        if not config_path.is_file() and (self.root / "opencode.json").is_file():
            config_path = self.root / "opencode.json"
        if self.check(config_path.is_file(), "DRIFT: opencode.json is missing (.opencode/ or root)"):
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self.fail(f"DRIFT: {config_path.relative_to(self.root)} is invalid JSON: {exc}")
                return
            if not isinstance(config, dict):
                self.fail(f"DRIFT: {config_path.relative_to(self.root)} must contain an object")
                return
            instructions = config.get("instructions") or []
            self.check(
                "my-workflows.md" in instructions,
                "DRIFT: opencode.json must load my-workflows.md",
            )
            skills = config.get("skills") or []
            skill_paths = skills if isinstance(skills, list) else skills.get("paths") or []
            self.check(
                ".opencode/skills" in skill_paths,
                "DRIFT: opencode.json must expose .opencode/skills",
            )
            permissions = config.get("permissions") or []
            denies_env = any(
                p.get("action") == "read"
                and "env" in str(p.get("resource", ""))
                and p.get("effect") == "deny"
                for p in permissions
            )
            if not denies_env:
                self.warn("WARN: opencode.json does not deny reading .env files")

    # ── Versions and paths ─────────────────────────────────────────────

    @staticmethod
    def major_minor(version: str) -> str:
        return ".".join(version.split(".")[:2])

    def versions(self, manifest: dict) -> None:
        expected = str(manifest.get("python_version") or "")
        if not expected:
            return
        agents = self.root / "AGENTS.md"
        if agents.is_file():
            match = re.search(r"Python\s+([0-9]+\.[0-9]+)", agents.read_text(encoding="utf-8"))
            if match:
                self.check(
                    match.group(1) == self.major_minor(expected),
                    f"DRIFT: AGENTS.md says Python {match.group(1)}, manifest says {expected}",
                )
        backend = (manifest.get("paths") or {}).get("python") or manifest.get("backend_path") or "."
        pyproject = self.root / backend / "pyproject.toml"
        if pyproject.is_file():
            match = re.search(
                r"requires-python\s*=\s*[\"'][^\"']*?([0-9]+\.[0-9]+)",
                pyproject.read_text(encoding="utf-8"),
            )
            if match:
                self.check(
                    match.group(1) == self.major_minor(expected),
                    f"DRIFT: {pyproject.relative_to(self.root)} requires Python "
                    f"{match.group(1)}, manifest says {expected}",
                )

    def paths(self, manifest: dict) -> None:
        for key, value in (manifest.get("paths") or {}).items():
            if value and value != "." and not (self.root / value).is_dir():
                self.warn(f"WARN: {key} path {value!r} does not exist yet")

    # ── Placeholders and required hooks ────────────────────────────────

    def placeholders(self) -> None:
        targets = [
            self.root / "AGENTS.md",
            self.root / "CLAUDE.md",
            self.root / "my-workflows.md",
        ]
        for folder in (".claude", ".opencode", ".githooks", ".github/workflows"):
            base = self.root / folder
            if base.is_dir():
                targets.extend(
                    p
                    for p in base.rglob("*")
                    if p.is_file() and p.suffix in {".md", ".json", ".sh", ".yml", ".yaml"}
                )
        for path in targets:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            match = PLACEHOLDER.search(text)
            if match:
                self.fail(
                    f"DRIFT: unresolved placeholder {match.group()} in "
                    f"{path.relative_to(self.root)}"
                )

    def hooks(self) -> None:
        for rel in (
            ".claude/hooks/check-project-drift.py",
            ".claude/hooks/check-secrets.py",
            ".claude/hooks/check-no-skipped-tests.sh",
            ".claude/hooks/check-primitive-drift.sh",
            ".claude/hooks/guardrails.sh",
            ".claude/hooks/install-git-hooks.sh",
            ".githooks/pre-commit",
            ".githooks/pre-push",
        ):
            self.check((self.root / rel).is_file(), f"DRIFT: required hook is missing: {rel}")

    # ── Runner ─────────────────────────────────────────────────────────

    def run(self) -> int:
        manifest = self.manifest()
        if manifest is not None:
            self.stacks(manifest)
            self.versions(manifest)
            self.paths(manifest)
        self.rule_index()
        self.map_lists()
        self.mirrors()
        self.context_files()
        self.placeholders()
        self.hooks()

        if not self.quiet:
            for warning in self.warnings:
                print(warning, file=sys.stderr)
        for error in self.errors:
            print(error, file=sys.stderr)
        if self.errors:
            print(f"FAIL: {len(self.errors)} project drift issue(s).", file=sys.stderr)
            return 1
        return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Check the rendered harness for project drift")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    checker = Drift(root, quiet=args.quiet)
    code = checker.run()
    if code == 0 and not args.quiet:
        print(f"PASS: project harness consistent ({checker.checks} checks)")
    return code

if __name__ == "__main__":
    sys.exit(main())
