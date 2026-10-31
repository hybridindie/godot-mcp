#!/usr/bin/env python3
"""Fetch unresolved, non-outdated review threads as compact data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

QUERY = """
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id isResolved isOutdated path line
          comments(first: 5) { nodes { author { login } body } }
        }
      }
    }
  }
}
"""

def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, timeout=30)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        repo = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").strip()
        owner, name = repo.split("/", 1)
        raw = gh("api", "graphql", "-f", f"query={QUERY}", "-F", f"owner={owner}", "-F", f"repo={name}", "-F", f"pr={args.pr}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"gh failed: {exc}", file=sys.stderr)
        return 1
    data = json.loads(raw)
    nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    threads = []
    for node in nodes:
        if node["isResolved"] or node["isOutdated"]:
            continue
        comments = node["comments"]["nodes"]
        threads.append({
            "id": node["id"],
            "path": node["path"] or "",
            "line": node["line"],
            "author": comments[-1]["author"]["login"] if comments else "",
            "body": comments[-1]["body"] if comments else "",
        })
    if args.json:
        print(json.dumps(threads, indent=2))
    else:
        for thread in threads:
            print(f"{thread['id']}\t{thread['path']}:{thread['line']}\t{thread['author']}\t{thread['body'][:800]}")
        print(f"unresolved={len(threads)}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
