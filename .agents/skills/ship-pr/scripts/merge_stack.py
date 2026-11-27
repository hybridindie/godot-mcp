#!/usr/bin/env python3
"""Merge a stack of reviewed PRs bottom-up, without rebasing between parts.

  merge_stack.py PR1 PR2 ... PRn [--dry-run]     (bottom part first)

Each part's checks and review cover its exact head commit. Once part k-1 is
on the base, the base holds part k-1's tree, so retargeting part k (its head,
and its checks, unchanged) and merging it lands the tree CI tested. A rebase
between merges would only rerun CI and review on code they passed.

Every part merges with a merge commit, whatever `merge_policy.method` says:
part k is based on part k-1's commits, and a squash or rebase leaves the base
without them, so git replays part k-1 from the old merge-base and part k
conflicts wherever it edits part k-1's lines (#178 follow-up, apeiron S7:
five of six squashed parts conflicted).

Every part must pass `merge_pr`'s gate before anything merges. Then, bottom
up: each part must be retargeted to the base with the head it was gated on
(a retarget fires no CI run, so the checks that head passed stand), and after
its merge every file its PR shows must match its tested head on the base.

Prints one JSON report. Exits:
  0  every part merged (with --dry-run: would merge)
  1  blocked: a gate or check failed (`merged` lists what landed first)
  3  a part needs a person (policy `never`, or an irreversible path)
  2  setup error: no forge access, an invalid policy, or not a stack
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

EXIT_MERGED, EXIT_BLOCKED, EXIT_SETUP, EXIT_PERSON = 0, 1, 2, 3
RETARGET_WAIT_SECONDS = 180
POLL_SECONDS = 10
# Squash or rebase would drop the history the next part is based on.
STACK_METHOD = "merge"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ship_pr_{name}", Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


merge_pr = load("merge_pr")
forge = merge_pr.forge


def stack_errors(views: list[dict]) -> list[str]:
    """Why the parts, bottom first, are not one stack; empty when they are."""
    errors = []
    heads = [v["head"] for v in views]
    if len(set(heads)) != len(heads):
        errors.append("a PR is listed twice")
    for below, part in zip(views, views[1:]):
        if part["base"] != below["head"]:
            errors.append(f"#{part['number']} targets {part['base']}, not #{below['number']}'s {below['head']}")
    return errors


def git(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:  # a timeout too: forge.py's rule
        raise forge.ForgeError(f"git {' '.join(args[:2])}: {exc}") from None


def fetch(ref: str) -> str:
    """The commit `ref` names on origin now."""
    proc = git("fetch", "-q", "origin", ref)
    if proc.returncode != 0:
        raise forge.ForgeError(f"git fetch origin {ref}: {proc.stderr.strip()}")
    sha = git("rev-parse", "FETCH_HEAD").stdout.strip()
    if not sha:
        raise forge.ForgeError(f"git rev-parse FETCH_HEAD after fetching {ref}: no commit")
    return sha


def differing(tested: str, landed: str, files: list[str]) -> list[str]:
    """The files that differ between the tested head and the landed base."""
    if not files:
        return []
    proc = git("diff", "--name-only", tested, landed, "--", *files)
    if proc.returncode != 0:
        raise forge.ForgeError(f"git diff {tested[:7]} {landed[:7]}: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


class Stack:
    def __init__(self, client, policy: dict, globs: list[str], has_ci: bool, *,
                 fetch=fetch, differing=differing, sleep=time.sleep, now=time.monotonic):
        self.client, self.policy, self.globs, self.has_ci = client, policy, globs, has_ci
        self.fetch, self.differing, self.sleep, self.now = fetch, differing, sleep, now
        self.seen: dict[int, list[dict]] = {}

    def gate(self, view: dict, gated: list[dict] | None = None) -> tuple[list[str], list[str]]:
        """(blocking reasons, reasons a person merges) for one part as it is now.
        `gated`: the checks this same head passed earlier, read when the forge
        lists none for it now (a retarget fires no `pull_request` run, but
        the head's runs still stand: the commit is the one they ran on)."""
        n = str(view["number"])
        checks = self.client.checks(n, required=True) or (gated or [])
        self.seen[view["number"]] = checks
        reasons = merge_pr.gate(view, checks, self.client.threads(n), self.has_ci, self.client.kind)
        person = []
        if self.policy["merge"] == "never":
            person.append("merge_policy.merge is never: a person merges")
        touched = merge_pr.irreversible(self.client.files(n), self.globs)
        if touched:
            person.append(f"irreversible paths need a person: {', '.join(touched[:10])}")
        return reasons, person

    def retargeted(self, view: dict, base: str) -> dict:
        """The part's view once the forge has moved it to `base` and settled
        its merge state, or as it stands when the wait runs out."""
        deadline = self.now() + RETARGET_WAIT_SECONDS
        while True:
            fresh = self.client.view(str(view["number"]))
            if fresh["base"] == base and fresh["merge_state"] != "UNKNOWN":
                return fresh
            if self.now() >= deadline:
                return fresh
            self.sleep(POLL_SECONDS)

    def run(self, numbers: list[str], dry_run: bool) -> tuple[int, dict]:
        views = [self.client.view(n) for n in numbers]
        report: dict = {"stack": [v["number"] for v in views], "policy": self.policy,
                        "method": STACK_METHOD, "merged": []}
        errors = stack_errors(views)
        if errors:
            return EXIT_SETUP, {**report, "decision": "error", "error": "; ".join(errors)}
        base = views[0]["base"]
        report["base"] = base
        held = []
        for v in views:
            reasons, person = self.gate(v)
            if reasons:
                return EXIT_BLOCKED, {**report, "decision": "blocked", "stopped_at": v["number"],
                                      "blocked_by": reasons}
            if person:
                held.append((v, person))
        if held:
            v, person = held[0]
            return EXIT_PERSON, {**report, "decision": "ready", "stopped_at": v["number"],
                                 "needs_person": person}
        if dry_run:
            return EXIT_MERGED, {**report, "decision": "would-merge"}
        tested = {v["number"]: self.fetch(v["head"]) for v in views}

        def stop(n: int, *why: str) -> tuple[int, dict]:
            return EXIT_BLOCKED, {**report, "decision": "blocked", "stopped_at": n, "blocked_by": list(why)}

        for k, v in enumerate(views):
            n, sha = v["number"], v["sha"]
            if tested[n] != sha:
                return stop(n, f"head moved since the gate: {sha[:7]} -> {tested[n][:7]}")
            if k:
                try:
                    fresh = self.retargeted(v, base)
                    reasons, _ = self.gate(fresh, gated=self.seen.get(n))
                except forge.ForgeError as exc:
                    return stop(n, f"re-gating #{n} after the retarget: {exc}")
                if fresh["base"] != base:
                    return stop(n, f"not retargeted to {base} (base is {fresh['base']})")
                if fresh["sha"] != sha:
                    return stop(n, f"head moved since the gate: {sha[:7]} -> {fresh['sha'][:7]}")
                if reasons:
                    return stop(n, *reasons)
            try:
                # Deleting the head branch closes PRs based on it: move them first.
                for d in self.client.dependents(v["head"]):
                    self.client.retarget(d, base)
                commit = self.client.merge(str(n), STACK_METHOD, sha)
            except forge.ForgeError as exc:
                return stop(n, f"merge of #{n}: {exc}")
            report["merged"].append({"pr": n, "merge_commit": commit})
            try:
                off = self.differing(sha, self.fetch(base), self.client.files(str(n)))
            except forge.ForgeError as exc:
                return stop(n, f"#{n} landed ({commit[:7]}), but checking its tree failed: {exc}")
            if off:
                return stop(n, f"#{n} landed, but {base} differs from its tested head in: {', '.join(off[:10])}")
        return EXIT_MERGED, {**report, "decision": "merged"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prs", nargs="+", help="PR numbers or URLs, bottom part first")
    ap.add_argument("--dry-run", action="store_true", help="gate every part; merge nothing")
    args = ap.parse_args()
    numbers = [p.rstrip("/").rsplit("/", 1)[-1] for p in args.prs]
    if not all(n.isdigit() for n in numbers):
        print(json.dumps({"decision": "error", "error": "every PR must be a number or URL"}, indent=2))
        return EXIT_SETUP
    try:
        policy = merge_pr.load_policy(merge_pr.repo_root())
        globs = merge_pr.irreversible_globs() + policy["irreversible_paths"]
        client = forge.connect()
        code, report = Stack(client, policy, globs, load("watch_pr").repo_has_ci()).run(numbers, args.dry_run)
    except merge_pr.PolicyError as exc:
        code, report = EXIT_SETUP, {"decision": "error", "error": f"merge_policy: {exc}"}
    except forge.ForgeError as exc:
        code, report = EXIT_SETUP, {"decision": "error", "error": str(exc)}
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
