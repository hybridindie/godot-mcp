#!/usr/bin/env python3
"""Merge a PR only when its gates pass and the repo's merge policy allows it.

  merge_pr.py [PR] [--dry-run]

Gates (every one must hold): the PR is open and not a draft, has no
`do-not-merge` label, the forge reports it mergeable (no conflict, not behind
where that blocks), every required check on the head passes (every check when
none is marked required; none reported where the repo defines CI is a fail),
no reviewer requests changes, and no blocking finding is open. A blocking
finding is any `Important —` (or unlabelled) finding nobody answered; on
GitHub any unresolved thread still blocks, as before.

Policy: `merge_policy` in `.claude/harness.json` (render.py writes the
default; a repo edits it, and re-renders keep it):

  "merge_policy": {
    "merge": "when-green",      # or "never": stop at ready-to-merge for a person
    "method": "merge",          # merge | squash | rebase
    "irreversible": "person",   # fixed: irreversible-lane paths always need a person
    "irreversible_paths": []    # globs added to the pipeline's irreversible lane
  }

The irreversible lane is `.agents/scripts/plan.py`'s IRREVERSIBLE_GLOBS (read,
not copied) plus `irreversible_paths`. A PR touching one is never merged here.

Prints one JSON report. Exits:
  0  merged (with --dry-run: would merge)
  1  blocked: a gate failed (reasons listed)
  3  ready, but a person merges (policy `never`, or an irreversible path)
  2  setup error: no forge access, or an invalid merge_policy
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_POLICY = {"merge": "when-green", "method": "merge", "irreversible": "person",
                  "irreversible_paths": []}
MODES = ("when-green", "never")
METHODS = ("merge", "squash", "rebase")
HOLD_LABELS = ("do-not-merge",)
EXIT_MERGED, EXIT_BLOCKED, EXIT_SETUP, EXIT_PERSON = 0, 1, 2, 3


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ship_pr_{name}", Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


forge = load("forge")


class PolicyError(ValueError):
    pass


def repo_root() -> Path:
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return Path(top) if top else Path.cwd()


def load_policy(root: Path) -> dict:
    """The repo's merge policy over the defaults. A missing file or key means
    the defaults; anything unreadable or unknown is an error, never a guess."""
    path = root / ".claude" / "harness.json"
    if not path.is_file():
        return dict(DEFAULT_POLICY)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"{path}: {exc}") from None
    raw = manifest.get("merge_policy") if isinstance(manifest, dict) else None
    if raw is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(raw, dict):
        raise PolicyError("merge_policy must be an object")
    unknown = set(raw) - set(DEFAULT_POLICY)
    if unknown:
        raise PolicyError(f"merge_policy has unknown keys: {', '.join(sorted(unknown))}")
    policy = {**DEFAULT_POLICY, **raw}
    if policy["merge"] not in MODES:
        raise PolicyError(f"merge_policy.merge must be one of {', '.join(MODES)}, not {policy['merge']!r}")
    if policy["method"] not in METHODS:
        raise PolicyError(f"merge_policy.method must be one of {', '.join(METHODS)}, not {policy['method']!r}")
    if policy["irreversible"] != "person":
        raise PolicyError("merge_policy.irreversible is always \"person\": an irreversible path is never auto-merged")
    paths = policy["irreversible_paths"]
    if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
        raise PolicyError("merge_policy.irreversible_paths must be a list of globs")
    return policy


def irreversible_globs() -> list[str]:
    """IRREVERSIBLE_GLOBS from the nearest `.agents/scripts/plan.py`, read with
    ast: importing plan.py may re-exec under uv to get PyYAML."""
    for parent in Path(__file__).resolve().parents:
        plan = parent / ".agents" / "scripts" / "plan.py"
        if plan.is_file():
            tree = ast.parse(plan.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "IRREVERSIBLE_GLOBS" for t in node.targets):
                    return [str(g) for g in ast.literal_eval(node.value)]
            raise PolicyError(f"{plan} has no IRREVERSIBLE_GLOBS")
    raise PolicyError(".agents/scripts/plan.py not found: cannot tell irreversible paths (re-render the harness)")


def glob_regex(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*` and `?` stay inside one; a pattern without
    a wildcard covers that file or everything below that directory (plan.py's rule)."""
    pattern = pattern.strip().replace("\\", "/").strip("/")
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if not any(ch in pattern for ch in "*?["):
        return re.compile(re.escape(pattern) + r"(?:/.*)?")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + r"(?:.*/)?", i + 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out, i = out + r"(?:/.*)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + r".*", i + 2
        elif pattern[i] == "*":
            out, i = out + r"[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + r"[^/]", i + 1
        elif pattern[i] == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out, i = out + re.escape("["), i + 1
            else:
                out, i = out + pattern[i:end + 1], end + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out)


def irreversible(paths: list[str], globs: list[str]) -> list[str]:
    compiled = [glob_regex(g) for g in globs]
    return [p for p in paths if any(rx.fullmatch(p.strip("/")) for rx in compiled)]


def gate(view: dict, checks: list[dict], threads: list[dict], has_ci: bool, kind: str) -> list[str]:
    """Every unmet merge condition, as a sentence; empty means mergeable."""
    reasons = []
    if view["state"] != "OPEN":
        reasons.append(f"PR is {view['state'].lower()}")
    if view["draft"]:
        reasons.append("PR is a draft")
    held = [lb for lb in view["labels"] if lb.casefold() in HOLD_LABELS]
    if held:
        reasons.append(f"labelled {', '.join(held)}")
    if view["merge_state"] != "CLEAN":
        reasons.append(f"merge state is {view['merge_state'].lower()} (conflict, behind, or protection)")
    if not checks:
        if has_ci:
            reasons.append("no checks reported on the head, but the repo defines CI")
    else:
        bad = [c["name"] for c in checks if c.get("bucket") not in ("pass", "skipping")]
        if bad:
            reasons.append(f"checks not green: {', '.join(sorted(bad))}")
    if view["changes_requested"]:
        reasons.append("a reviewer requested changes")
    open_ = [t for t in threads if not t["answered"]]
    blocking = open_ if kind == "github" else [t for t in open_ if t["severity"] != "nit"]
    if blocking:
        where = ", ".join(f"{t['path']}:{t['line']}" for t in blocking[:5])
        reasons.append(f"{len(blocking)} finding(s) not fixed or answered: {where}")
    return reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", nargs="?", help="PR number or URL (default: the current branch's)")
    ap.add_argument("--dry-run", action="store_true", help="report the decision; merge nothing")
    args = ap.parse_args()
    report: dict = {"pr": None}
    try:
        policy = load_policy(repo_root())
        globs = irreversible_globs() + policy["irreversible_paths"]
        client = forge.connect()
        number = (args.pr or "").rstrip("/").rsplit("/", 1)[-1]
        if not number.isdigit():
            found = client.find()
            if not found:
                raise forge.ForgeError("no pull request for the current branch")
            number = str(found["number"])
        view = client.view(number)
        checks = client.checks(number, required=True)
        threads = client.threads(number)
        touched = irreversible(client.files(number), globs)
    except PolicyError as exc:
        print(json.dumps({"decision": "error", "error": f"merge_policy: {exc}"}, indent=2))
        return EXIT_SETUP
    except forge.ForgeError as exc:
        print(json.dumps({"decision": "error", "error": str(exc)}, indent=2))
        return EXIT_SETUP

    watch = load("watch_pr")
    reasons = gate(view, checks, threads, watch.repo_has_ci(), client.kind)
    person = []
    if policy["merge"] == "never":
        person.append("merge_policy.merge is never: a person merges")
    if touched:
        person.append(f"irreversible paths need a person: {', '.join(touched[:10])}")
    report = {
        "pr": view["number"], "url": view["url"], "forge": client.kind, "policy": policy,
        "blocked_by": reasons, "needs_person": person, "irreversible_paths": touched,
        "open_findings": sum(1 for t in threads if not t["answered"]),
    }
    if reasons:
        print(json.dumps({**report, "decision": "blocked"}, indent=2))
        return EXIT_BLOCKED
    if person:
        print(json.dumps({**report, "decision": "ready"}, indent=2))
        return EXIT_PERSON
    if args.dry_run:
        print(json.dumps({**report, "decision": "would-merge"}, indent=2))
        return EXIT_MERGED
    retargeted: list[int] = []
    try:
        # Deleting the head branch closes PRs based on it: move them to our base first.
        for n in client.dependents(view["head"]):
            client.retarget(n, view["base"])
            retargeted.append(n)
        commit = client.merge(number, policy["method"], view["sha"])
    except forge.ForgeError as exc:  # already-retargeted PRs are listed: that step is not undone
        print(json.dumps({**report, "decision": "blocked", "blocked_by": [f"merge refused: {exc}"],
                          "retargeted": retargeted}, indent=2))
        return EXIT_BLOCKED
    print(json.dumps({**report, "decision": "merged", "merge_commit": commit, "retargeted": retargeted},
                     indent=2))
    return EXIT_MERGED


if __name__ == "__main__":
    sys.exit(main())
