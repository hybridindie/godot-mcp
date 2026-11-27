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
  4. The Claude/OpenCode mirrors have the same commands and agents, every
     .agents/skills skill has its .claude/skills pointer, and every pipeline
     file a skill names (`.agents/scripts/plan.py`, doctrine, templates,
     rubrics) exists.
  5. `CLAUDE.md` stays a thin import of `AGENTS.md`.
  6. The Python version in `AGENTS.md` and `pyproject.toml` matches the manifest.
  7. No rendered placeholder survived.
  8. The expected hooks and git hooks exist.

Exit 0 when clean, 1 when drift is found. Use --quiet in git hooks.
"""

from __future__ import annotations

import argparse
import json
import os
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
}
# Keep in sync with LEGACY_PROFILES in genesis templates/scripts/render.py.
LEGACY_PROFILES = {
    "web": ["fastapi", "frontend"], "fastapi+react": ["fastapi", "frontend"],
    "generic-python": ["python"],
}

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
            data.setdefault("packs", [])
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
            raw_aliases = manifest.get("rule_aliases")
            aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
            for name, marker in sorted(markers.items()):
                # A tailored repo may cover a stack under its own rule name
                # (`rule_aliases` in harness.json, e.g. rust -> native.md).
                alias = aliases.get(name)
                if name in declared and isinstance(alias, str) and alias:
                    marker = alias
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

        # A skill is a directory with a SKILL.md, or a link to one outside the
        # repo (a skill linked to a sibling checkout dangles where that
        # checkout is absent, as in CI, and still counts).
        skills_root = self.root / ".claude" / "skills"
        skill_dirs = {
            p.name
            for p in (skills_root.iterdir() if skills_root.is_dir() else [])
            if (p / "SKILL.md").is_file() or p.is_symlink()
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
        left = {p.stem for p in (self.root / ".claude" / "commands").glob("*.md")}
        right = {p.stem for p in (self.root / ".opencode" / "commands").glob("*.md")}
        for missing in sorted(left - right):
            self.fail(f"DRIFT: .opencode/commands is missing {missing}")
        for extra in sorted(right - left):
            self.fail(f"DRIFT: .opencode/commands has no Claude counterpart: {extra}")
        # Skills live once in .agents/skills/ (OpenCode reads it); Claude Code
        # gets a pointer per skill in .claude/skills/. No .opencode/skills copy.
        skills = {p.parent.name for p in (self.root / ".agents" / "skills").glob("*/SKILL.md")}
        pointers = {p.parent.name for p in (self.root / ".claude" / "skills").glob("*/SKILL.md")}
        for missing in sorted(skills - pointers):
            self.fail(f"DRIFT: .claude/skills is missing the pointer for {missing}")
        for extra in sorted(pointers - skills):
            text = (self.root / ".claude" / "skills" / extra / "SKILL.md").read_text(encoding="utf-8")
            if f".agents/skills/{extra}/SKILL.md" in text:
                self.fail(f"DRIFT: .claude/skills/{extra} points at a missing .agents/skills/{extra}")
            elif "generated by scripts/sync-skill-wrappers.py" not in text:
                self.warn(f"WARN: .claude/skills/{extra} is not a generated pointer: a stale copy, or a "
                          f"project skill only Claude Code sees (move it to .agents/skills/{extra}/)")
        for old in sorted((self.root / ".opencode" / "skills").glob("*/SKILL.md")):
            self.warn(f"WARN: {old.relative_to(self.root)} duplicates a skill; skills live in .agents/skills/")
        if (self.root / ".claude" / "agents").is_dir():
            left = {p.name for p in (self.root / ".claude" / "agents").glob("*.md")}
            right = {p.name for p in (self.root / ".opencode" / "agents").glob("*.md")}
            for missing in sorted(left - right):
                self.fail(f"DRIFT: .opencode/agents is missing {missing}")
            for extra in sorted(right - left):
                self.fail(f"DRIFT: .opencode/agents has no Claude counterpart: {extra}")

    # Files a skill names under these .agents/ folders ship with the harness
    # (the plan-and-dispatch pipeline); `.agents/plan-constraints.yaml` is the
    # project's own and only exists once a lesson is recorded.
    PIPELINE_REF = re.compile(r"(?<![\w/~-])\.agents/(?:scripts|doctrine|templates|evals)/[\w./-]*\w\.(?:py|md)")

    def pipeline(self) -> None:
        for skill in sorted((self.root / ".agents" / "skills").glob("*/SKILL.md")):
            for rel in sorted(set(self.PIPELINE_REF.findall(skill.read_text(encoding="utf-8")))):
                self.check((self.root / rel).is_file(),
                           f"DRIFT: {skill.relative_to(self.root)} uses {rel}, which is missing")
        for script in sorted((self.root / ".agents" / "scripts").glob("*.py")):
            self.check(os.access(script, os.X_OK),
                       f"DRIFT: {script.relative_to(self.root)} is not executable")

    # ── Context files ──────────────────────────────────────────────────

    def context_files(self) -> None:
        claude = self.root / "CLAUDE.md"
        if self.check(claude.is_file(), "DRIFT: CLAUDE.md is missing"):
            text = claude.read_text(encoding="utf-8")
            self.check("@AGENTS.md" in text, "DRIFT: CLAUDE.md must import @AGENTS.md")
            self.check(
                len(text.splitlines()) <= 60,
                "DRIFT: CLAUDE.md is no longer thin; move content to AGENTS.md",
            )
        # OpenCode merges a root opencode.json and .opencode/opencode.json; check both.
        paths = [p for p in (self.root / "opencode.json", self.root / ".opencode" / "opencode.json")
                 if p.is_file()]
        if not self.check(bool(paths), "DRIFT: no opencode.json (root or .opencode/)"):
            return
        configs = []
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self.fail(f"DRIFT: {path.relative_to(self.root)} is invalid JSON: {exc}")
                continue
            if isinstance(data, dict):
                configs.append(data)
            else:
                self.fail(f"DRIFT: {path.relative_to(self.root)} must contain an object")
        if not configs:
            return  # every file was reported above; don't also claim one is missing
        skill_paths = []
        for config in configs:
            skill_paths += self.path_list(config.get("skills"))
        # Skills live in .agents/skills/, which OpenCode discovers without config.
        stale = [p for p in skill_paths if str(p).rstrip("/").endswith(".opencode/skills")]
        if stale and not (self.root / ".opencode" / "skills").is_dir():
            self.warn("WARN: opencode.json points skills at .opencode/skills, which no longer exists")
        if not any(self.denies_env(c) for c in configs):
            self.warn("WARN: opencode.json does not deny reading .env files")

    @staticmethod
    def path_list(value: object) -> list:
        """`instructions`/`skills` arrive as a list, one string, or `{paths: [...]}`.

        OpenCode accepts all three; treating a bare string as iterable splits it
        into characters and reports drift for a config that is actually fine.
        """
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            paths = value.get("paths")
            return paths if isinstance(paths, list) else []
        return []

    @staticmethod
    def is_env_path(value: str) -> bool:
        """`.env` and its variants, not `.env.example` or an `environments/` dir."""
        # Globs (`*.env`, `**/.env*`) and bash denies (`cat *.env*`) name the
        # same files: take the last path's file-name token, its stars dropped.
        parts = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].split()
        name = (parts[-1] if parts else "").strip("*")
        return name == ".env" or (
            name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))
        )

    # The tools a `{pattern: "deny"}` shorthand guards reads under.
    READ_TOOLS = (None, "read", "bash")

    @staticmethod
    def denies_env(node: object, tool: str | None = None) -> bool:
        """Accepts the v2 `permissions` list and the `permission` object form.

        A `{pattern: "deny"}` shorthand counts only under a read-capable tool
        (`tool`, the key it sits under): an `edit`-only deny leaves reads open.
        A blanket `"read": "deny"` covers `.env` too.
        """
        if isinstance(node, dict):
            action = node.get("action")
            if (node.get("effect") == "deny"
                    and Drift.is_env_path(str(node.get("resource", "")))
                    and action in (None, "read")):
                return True
            if node.get("read") == "deny":
                return True
            if tool in Drift.READ_TOOLS and any(
                Drift.is_env_path(str(k)) and v == "deny" for k, v in node.items()
            ):
                return True
            return any(
                Drift.denies_env(v, tool if k in ("permission", "permissions") else k)
                for k, v in node.items()
            )
        if isinstance(node, list):
            return any(Drift.denies_env(v, tool) for v in node)
        return False

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
        ):
            self.check((self.root / rel).is_file(), f"DRIFT: required hook is missing: {rel}")
        for rel in (".githooks/pre-commit", ".githooks/pre-push"):
            if not (self.root / rel).is_file():  # repos on pre-commit or another hooksPath
                self.warn(f"WARN: {rel} is missing; make sure another hook runs guardrails.sh")

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
        self.pipeline()
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
