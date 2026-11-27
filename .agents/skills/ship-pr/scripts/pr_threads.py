#!/usr/bin/env python3
"""Review findings on a PR: list the open ones, reply, resolve. GitHub or Gitea.

  pr_threads.py --pr N [--json] [--all]       open findings (all of them with --all)
  pr_threads.py --pr N --reply ID --body TEXT [--resolve]
  pr_threads.py --pr N --resolve ID

Open means: on GitHub, a thread neither resolved nor outdated; on Gitea, which
has no GraphQL, a finding nobody answered (see forge.Gitea.threads: resolved,
replied to by the PR's author or the token's user, or followed by a commit).
On Gitea a reply goes into the finding's thread, or into the PR conversation
with a marker naming the finding where the server has no reply endpoint;
resolving is skipped where the server can't.

Exits 0 on success, 1 on a forge error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_forge():
    spec = importlib.util.spec_from_file_location("ship_pr_forge", Path(__file__).with_name("forge.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


forge = load_forge()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--all", action="store_true", help="list answered findings too")
    parser.add_argument("--reply", metavar="ID", help="thread (GitHub) or review comment (Gitea) to answer")
    parser.add_argument("--body", help="reply text")
    parser.add_argument("--resolve", nargs="?", const=True, metavar="ID",
                        help="resolve ID, or with --reply the thread just answered")
    args = parser.parse_args()
    if args.reply and not args.body:
        parser.error("--reply needs --body")
    if args.resolve is True and not args.reply:
        parser.error("--resolve needs an ID without --reply")
    try:
        f = forge.connect()
        if args.reply:
            made = f.reply(args.pr, args.reply, args.body)
            if args.resolve:
                made["resolved"] = f.resolve(args.reply)
            print(json.dumps(made))
            return 0
        if args.resolve:
            print(json.dumps({"thread": args.resolve, "resolved": f.resolve(args.resolve)}))
            return 0
        threads = f.threads(args.pr)
    except forge.ForgeError as exc:
        print(f"pr_threads: {exc}", file=sys.stderr)
        return 1
    shown = threads if args.all else [t for t in threads if not t["answered"]]
    if args.json:
        keys = ("id", "path", "line", "author", "body", "severity") + (("answered", "answered_by") if args.all else ())
        print(json.dumps([{k: t.get(k) for k in keys} for t in shown], indent=2))
    else:
        for thread in shown:
            print(f"{thread['id']}\t{thread['path']}:{thread['line']}\t{thread['author']}\t{thread['body'][:800]}")
        print(f"unresolved={sum(1 for t in threads if not t['answered'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
