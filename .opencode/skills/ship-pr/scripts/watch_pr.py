#!/usr/bin/env python3
"""
Watch a pull request until CI and the PR-agent review settle.

Exits:
  0   settled — CI finished and the review state is known (see output)
  10  CI failed
  20  changes requested
  30  blocked (draft, conflicts, behind base, or approval required)
  40  timeout
  50  merged or closed
  2   setup error (no gh, no PR, auth)

Uses only the gh CLI and the standard library. Notifies through Herdr when
HERDR_ENV=1, otherwise it prints the result; the caller redirects stdout to a
log for background runs.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_BOTS = ("qodo", "pr-agent", "coderabbit", "sourcery", "greptile")
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

def bot_names():
    override = os.environ.get("SHIP_PR_BOTS", "").strip()
    if override:
        return tuple(x.strip().lower() for x in override.split(",") if x.strip())
    return DEFAULT_BOTS if Path(".pr_agent.toml").is_file() else ()

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

def latest_bot_activity(pr, bots):
    if not bots:
        return None
    times = []
    for review in pr.get("reviews") or []:
        login = ((review.get("author") or {}).get("login") or "").lower()
        if any(bot in login for bot in bots):
            times.append(parse_time(review.get("submittedAt")))
    for comment in pr.get("comments") or []:
        login = ((comment.get("author") or {}).get("login") or "").lower()
        if any(bot in login for bot in bots):
            times.append(parse_time(comment.get("createdAt")))
    known = [t for t in times if t is not None]
    return max(known) if known else None

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

    if checks is not None:
        if checks["fail"] or checks["cancel"]:
            return 10, "ci_failed", "one or more checks failed"
        if checks["pending"]:
            return None, "waiting", "checks still running"

    if merge_state in ("DIRTY", "BEHIND"):
        return 30, "blocked", f"merge state is {merge_state.lower()}"

    if bots:
        bot_time = latest_bot_activity(pr, bots)
        commit_time = last_commit_time(pr)
        if bot_time is None or (commit_time and bot_time < commit_time):
            return None, "waiting", "waiting for the PR-agent review"
        if decision == "APPROVED":
            return 0, "settled", "review approved and CI green"
        if decision == "REVIEW_REQUIRED" and merge_state == "BLOCKED":
            return 0, "settled", "review landed; approval still required"
        return 0, "settled", "review landed and CI green"

    # No PR-agent configured: stop when checks are done and report the state.
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

    if not shutil.which("gh"):
        print("ERROR: gh CLI not found", file=sys.stderr)
        return 2

    pr_number = None
    if args.pr:
        tail = args.pr.rstrip("/").split("/")[-1]
        pr_number = tail if tail.isdigit() else None
    if pr_number is None:
        current = gh_json(["pr", "view", "--json", "number"])
        if not current:
            print("ERROR: no pull request for the current branch", file=sys.stderr)
            return 2
        pr_number = current["number"]

    bots = bot_names()
    deadline = time.monotonic() + max(args.timeout, 0)
    interval = max(args.interval, 5)
    print(f"Watching PR #{pr_number} (bots: {', '.join(bots) or 'none detected'})", flush=True)

    while True:
        pr = gh_json(["pr", "view", str(pr_number), "--json", FIELDS])
        if not pr:
            print("ERROR: could not read the pull request (auth or network?)", file=sys.stderr)
            return 2
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
