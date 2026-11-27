#!/usr/bin/env python3
"""
Watch a pull request until CI and the automated review settle.

Exits:
  0   settled — CI finished and the review state is known (see output)
  10  CI failed
  20  changes requested
  30  blocked (draft, conflicts, behind base, or approval required)
  40  timeout
  50  merged or closed
  2   setup error (no gh, no PR, auth, no Gitea token)

Note: an empty check list is pending in a repo with workflow files, and
settles only in a repo without them.

The forge comes from `forge.py` (the `origin` remote, as tracker.py reads it).
GitHub uses the gh CLI; Gitea uses its REST API, mapped onto the same fields
`gh pr view` gives, so both forges settle by one rule. Standard library only. Notifies through Herdr when
HERDR_ENV=1, otherwise it prints the result; the caller redirects stdout to a
log for background runs.
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# A repo-level marker says an automated reviewer is configured, but not which
# one: the reviewer can be swapped out cluster-side while `.pr_agent.toml`
# files stay behind, so the marker only decides whether to wait. A GitHub App
# posts as `<slug>[bot]` and the slug is deployment-specific, so any bot login
# counts as a reviewer unless it is the kind that only reports dependencies or
# build output. Set SHIP_PR_BOTS to name a reviewer outright, or `none` to
# never wait for one.
REVIEW_MARKERS = (".opencodereview/rule.json", ".pr_agent.toml")
KNOWN_REVIEWERS = (
    "open-code-review", "opencodereview", "ocr",
    "qodo", "qodo-merge", "pr-agent", "coderabbitai", "sourcery-ai", "greptile-app",
)
# Bots that comment constantly but never review; waiting on them would stall.
IGNORED_BOTS = ("dependabot", "renovate", "github-actions", "codecov", "snyk", "copilot")
CHECKS_GRACE_SECONDS = 180
# A repo defines CI when either forge's workflow directory holds a file. A
# project rendered with --no-ci has none, so an empty check list there is final.
WORKFLOW_DIRS = (".github/workflows", ".gitea/workflows")


def load_forge():
    spec = importlib.util.spec_from_file_location("ship_pr_forge", Path(__file__).with_name("forge.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


forge = load_forge()
FIELDS = (
    "number,url,state,isDraft,mergeStateStatus,reviewDecision,"
    "statusCheckRollup,reviews,comments,commits,labels"
)


def gh(args, timeout=60):
    try:
        return subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def gh_json(args, timeout=60):
    p = gh(args, timeout)
    if not p or not p.stdout.strip():
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def bot_names(pr=None):
    override = os.environ.get("SHIP_PR_BOTS", "").strip()
    if override:
        if override.lower() == "none":
            return ()
        return tuple(x.strip().lower() for x in override.split(",") if x.strip())
    if any(Path(marker).is_file() for marker in REVIEW_MARKERS):
        return KNOWN_REVIEWERS
    if pr is not None:
        # No marker: a cluster-side reviewer still shows up in the PR history.
        logins = [
            ((item.get("author") or {}).get("login") or "")
            for item in (pr.get("reviews") or []) + (pr.get("comments") or [])
        ]
        if any(is_reviewer(x, KNOWN_REVIEWERS) for x in logins):
            return KNOWN_REVIEWERS
    return ()


def matches_bot(login, bots):
    """Loose login match: `ocr` covers `ocr-reviewer[bot]` and `acme-ocr[bot]`,
    but not `mediocre-dev`."""
    login = (login or "").lower()
    if login.endswith("[bot]"):
        login = login[: -len("[bot]")]
    return any(
        login == bot
        or login.startswith((bot + "-", bot + "_", bot + "."))
        or login.endswith(("-" + bot, "_" + bot))
        for bot in bots
    )


def repo_has_ci():
    """Workflow files at the repository root (the repo `gh` targets), wherever we run from."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    root = Path(top) if top else Path.cwd()
    return any(
        p.is_file() for d in WORKFLOW_DIRS if (root / d).is_dir() for p in (root / d).iterdir()
    )


def check_buckets(pr_number):
    data = gh_json(["pr", "checks", str(pr_number), "--json", "bucket,name,state,link"])
    if data is None:
        return None
    counts = {"pass": 0, "pending": 0, "fail": 0, "skipping": 0, "cancel": 0}
    for item in data:
        bucket = (item.get("bucket") or "pending").lower()
        if bucket in counts:
            counts[bucket] += 1
        elif bucket in ("pending", "queued", "in_progress"):
            counts["pending"] += 1
    counts["total"] = len(data)
    return counts


def is_reviewer(login, bots):
    """A configured reviewer, or any bot that is not a dependency/build reporter."""
    if matches_bot(login, bots):
        return True
    low = (login or "").lower()
    if any(name in low for name in IGNORED_BOTS):
        return False
    # `gh pr view` reports an App's author as the bare slug, without the `[bot]`
    # suffix the REST API appends, so match the common bot/reviewer suffixes too.
    return low.endswith(("[bot]", "-bot", "-reviewer", "-app", "-ai"))


def latest_bot_activity(pr, bots):
    if not bots:
        return None
    times = []
    for review in pr.get("reviews") or []:
        login = (review.get("author") or {}).get("login") or ""
        if is_reviewer(login, bots):
            times.append(parse_time(review.get("submittedAt")))
    for comment in pr.get("comments") or []:
        login = (comment.get("author") or {}).get("login") or ""
        if is_reviewer(login, bots):
            # A reviewer that edits one summary comment in place each round
            # (OpenCodeReview) is only newer than the commit by its edit time.
            times.append(parse_time(comment.get("createdAt")))
            times.append(parse_time(comment.get("updatedAt")))
    known = [t for t in times if t is not None]
    return max(known) if known else None


def with_edit_times(pr):
    """Add each comment's REST `updated_at` as `updatedAt` (genesis#142).

    `gh pr view --json comments` carries no edit time. If the REST read fails,
    the comments keep only `createdAt` and the watch behaves as before."""
    match = re.match(r"https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)", pr.get("url") or "")
    if not match:
        return pr
    owner, repo, number = match.groups()
    p = gh([
        "api", f"repos/{owner}/{repo}/issues/{number}/comments", "--paginate",
        "--jq", r'.[] | [.html_url, .updated_at] | @tsv',
    ])
    if not p or p.returncode != 0:
        return pr
    edited = {}
    for line in p.stdout.splitlines():
        url, _, updated = line.partition("\t")
        if url and updated:
            edited[url] = updated
    for comment in pr.get("comments") or []:
        updated = edited.get(comment.get("url"))
        if updated:
            comment["updatedAt"] = updated
    return pr


def last_commit_time(pr):
    commits = pr.get("commits") or []
    if not commits:
        return None
    return parse_time(commits[-1].get("committedDate"))


def evaluate(pr, checks, bots):
    state = pr.get("state")
    if state in ("MERGED", "CLOSED"):
        return 50, "closed", f"PR is {state.lower()}"

    if pr.get("isDraft"):
        return 30, "draft", "PR is a draft — mark it ready for review first"

    decision = (pr.get("reviewDecision") or "").upper()
    merge_state = (pr.get("mergeStateStatus") or "").upper()

    if decision == "CHANGES_REQUESTED":
        return 20, "changes_requested", "review requested changes"

    no_ci = False
    if not checks or not checks["total"]:
        # `gh pr checks` reports nothing both while CI registers and when no run
        # was triggered at all — e.g. after a retarget, since `pull_request` does
        # not fire on a base edit. In a repo that defines CI an empty list is
        # pending, never settled: a PR with no checks must not look mergeable.
        # Without workflow files it is final once the grace period ends.
        if pr.get("statusCheckRollup"):
            return None, "waiting", "checks are registering"
        commit_time = last_commit_time(pr)
        if commit_time and (datetime.now(timezone.utc) - commit_time).total_seconds() < CHECKS_GRACE_SECONDS:
            return None, "waiting", "checks are registering"
        if merge_state in ("DIRTY", "BEHIND"):  # a reopen won't fix conflicts
            return 30, "blocked", f"merge state is {merge_state.lower()}"
        if repo_has_ci():
            return None, "waiting", (
                "no checks reported — if the base was retargeted, "
                "close and reopen the PR to trigger CI"
            )
        no_ci = True
    elif checks["fail"] or checks["cancel"]:
        return 10, "ci_failed", "one or more checks failed"
    elif checks["pending"]:
        return None, "waiting", "checks still running"

    if merge_state in ("DIRTY", "BEHIND"):
        return 30, "blocked", f"merge state is {merge_state.lower()}"

    if bots:
        bot_time = latest_bot_activity(pr, bots)
        commit_time = last_commit_time(pr)
        if bot_time is None or (commit_time and bot_time < commit_time):
            return None, "waiting", "waiting for the automated review"
        if no_ci:
            return 0, "settled", "review landed; repo has no CI (no workflow files)"
        if decision == "APPROVED":
            return 0, "settled", "review approved and CI green"
        if decision == "REVIEW_REQUIRED" and merge_state == "BLOCKED":
            return 30, "blocked", "review landed; approval still required"
        return 0, "settled", "review landed and CI green"

    # No automated reviewer configured: stop when checks are done and report the state.
    if no_ci:
        return 0, "settled", "repo has no CI (no workflow files); review status reported"
    if decision == "APPROVED":
        return 0, "settled", "review approved and CI green"
    return 0, "settled", "checks finished; review status reported"


def notify(status, message, pr_number):
    if os.environ.get("HERDR_ENV") != "1" or not shutil.which("herdr"):
        return
    sound = "done" if status == "settled" else "request"
    subprocess.run(
        [
            "herdr",
            "notification",
            "show",
            f"PR #{pr_number}: {status.replace('_', ' ')}",
            "--body",
            message,
            "--sound",
            sound,
        ],
        capture_output=True,
        text=True,
    )


def summary(pr, checks, status, message):
    decision = pr.get("reviewDecision") or "none"
    merge_state = pr.get("mergeStateStatus") or "unknown"
    checks_text = (
        f"{checks['pass']}/{checks['total']} pass, {checks['pending']} pending, "
        f"{checks['fail']} fail"
        if checks
        else "no checks reported"
    )
    print(
        json.dumps(
            {
                "pr": pr.get("number"),
                "url": pr.get("url"),
                "status": status,
                "message": message,
                "checks": checks_text,
                "review_decision": decision,
                "merge_state": merge_state,
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Watch a PR until CI and review settle")
    parser.add_argument("pr", nargs="?", help="PR number or URL (default: current branch)")
    parser.add_argument("--timeout", type=int, default=1200, help="seconds before giving up (default 1200)")
    parser.add_argument("--interval", type=int, default=20, help="initial poll interval (default 20s)")
    parser.add_argument("--once", action="store_true", help="evaluate once and exit")
    args = parser.parse_args()

    try:
        client = forge.connect()
    except forge.ForgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    gitea = client.kind == "gitea"
    if not gitea and not shutil.which("gh"):
        print("ERROR: gh CLI not found", file=sys.stderr)
        return 2

    pr_number = None
    if args.pr:
        tail = args.pr.rstrip("/").split("/")[-1]
        pr_number = tail if tail.isdigit() else None
    if pr_number is None:
        try:
            current = client.find() if gitea else gh_json(["pr", "view", "--json", "number"])
        except forge.ForgeError:
            current = None
        if not current:
            print("ERROR: no pull request for the current branch", file=sys.stderr)
            return 2
        pr_number = current["number"]

    bots = None
    deadline = time.monotonic() + max(args.timeout, 0)
    interval = max(args.interval, 5)

    while True:
        if gitea:
            try:
                pr, checks = client.gh_view(pr_number)
            except forge.ForgeError as exc:
                print(f"ERROR: could not read the pull request: {exc}", file=sys.stderr)
                return 2
        else:
            pr = gh_json(["pr", "view", str(pr_number), "--json", FIELDS])
            if not pr:
                print("ERROR: could not read the pull request (auth or network?)", file=sys.stderr)
                return 2
            pr = with_edit_times(pr)
        detected = bot_names(pr)
        if detected != bots:
            # Re-detect until a reviewer shows up: a cluster-side reviewer that
            # has not posted yet leaves the first poll empty, and caching that
            # empty result would settle before the mandated review.
            bots = detected
            print(
                f"Watching PR #{pr_number} (reviewers: {', '.join(bots) or 'none detected'})",
                flush=True,
            )
        if not gitea:
            checks = check_buckets(pr_number)
        code, status, message = evaluate(pr, checks, bots)

        if code is None:
            print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)
            if args.once or time.monotonic() >= deadline:
                print("Timed out waiting for the PR to settle.", file=sys.stderr)
                notify("timeout", message, pr_number)
                summary(pr, checks, "timeout", message)
                return 40
            time.sleep(interval)
            interval = min(interval + 10, 60)
            continue

        notify(status, message, pr_number)
        summary(pr, checks, status, message)
        return code


if __name__ == "__main__":
    sys.exit(main())
