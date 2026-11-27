#!/usr/bin/env python3
"""Read and write Epic/story issue bodies on GitHub or Gitea.

  tracker.py get    REF [-o FILE]              print (or save) the issue body
  tracker.py put    REF FILE                   replace the issue body with FILE
  tracker.py create --title T --body-file F [--label NAME...]
                                               open an issue, labelled; prints its number
  tracker.py comment REF --body TEXT           add a comment
  tracker.py labels REF                        print the issue's label names, one per line
  tracker.py label  REF [--add NAME...] [--remove NAME...]
                                               add/remove labels (missing ones are created)
  tracker.py author REF                        print the login that opened the issue
  tracker.py list [--state open|closed|all] [--label NAME...] [--title-prefix TEXT]
                                               print issues as JSON, oldest first

REF is `#13`, `13`, or a full issue URL. The forge comes from the `origin`
remote: github.com uses the `gh` CLI (already authenticated); anything else is
treated as Gitea and uses its REST API with `GITEA_TOKEN` (or `TEA_TOKEN`).
Set `TRACKER=github|gitea` to override detection.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Approval labels are a person's decision; an agent never applies them.
HUMAN_ONLY_LABELS = ("factory:approved", "factory:auto-approve")
NEW_LABEL_COLOR = "ededed"


class LabelRefused(ValueError):
    """A label change an agent may not make, or an ambiguous one."""


class GiteaError(RuntimeError):
    """A failed Gitea REST call; `status` is the HTTP code, or None when unreachable."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def canonical(name: str) -> str:
    """How labels compare: case and every space ignored."""
    return re.sub(r"\s+", "", name).casefold()


def check_labels(add: list[str], remove: list[str]) -> tuple[list[str], list[str]]:
    """Strip and de-duplicate names; refuse approval labels and a name both added and removed.

    Every forge's `label` calls this, so library callers get the same guard as the CLI."""
    add = list({canonical(n): n.strip() for n in add if n.strip()}.values())
    remove = list({canonical(n): n.strip() for n in remove if n.strip()}.values())
    for verb, names in (("add", add), ("remove", remove)):
        refused = [n for n in names if canonical(n) in {canonical(h) for h in HUMAN_ONLY_LABELS}]
        if refused:  # a person applies and withdraws approval, never an agent
            raise LabelRefused(f"refusing to {verb} {', '.join(refused)}: a person applies that label, not an agent")
    clash = {canonical(n) for n in add} & {canonical(n) for n in remove}
    if clash:
        raise LabelRefused(f"a label can't be both added and removed: {', '.join(sorted(clash))}")
    return add, remove


def sh(*cmd: str, stdin: str | None = None) -> str:
    try:
        out = subprocess.run(cmd, input=stdin, capture_output=True, text=True, check=True, timeout=60)
    except FileNotFoundError:
        sys.exit(f"tracker: {cmd[0]} is not installed")
    except subprocess.TimeoutExpired:
        sys.exit(f"tracker: {' '.join(cmd[:3])} timed out after 60s")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"tracker: {' '.join(cmd[:3])} failed: {exc.stderr.strip()}")
    return out.stdout


def parse_remote(url: str) -> tuple[str, str, str, str]:
    """(host, web base URL, owner, repo) from a git remote URL.

    Owner and repo are the last two path segments; anything before them is a
    sub-path the forge is served under. An https remote keeps its port; an ssh
    port is the ssh daemon's, so the web base falls back to https://host
    (GITEA_URL overrides it).
    """
    url = url.strip()
    m = re.match(r"^(https?)://(?:[^@/]+@)?([^/:]+)(:\d+)?/(.+)$", url)
    if m:
        scheme, host, port, path = m.group(1), m.group(2), m.group(3) or "", m.group(4)
    else:
        m = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^/:]+)(?::\d+/|:|/)(.+)$", url)
        if not m:
            sys.exit(f"tracker: cannot parse origin remote {url!r}")
        scheme, host, port, path = "https", m.group(1), "", m.group(2)
    parts = [s for s in re.sub(r"\.git/?$", "", path).strip("/").split("/") if s]
    if len(parts) < 2:
        sys.exit(f"tracker: cannot find owner/repo in origin remote {url!r}")
    prefix = "/".join(parts[:-2])
    base = f"{scheme}://{host}{port}" + (f"/{prefix}" if prefix else "")
    return host, base, parts[-2], parts[-1]


def remote() -> tuple[str, str, str, str]:
    return parse_remote(sh("git", "remote", "get-url", "origin"))


def number(ref: str) -> str:
    """The issue number from `#13`, `13` or an issue URL (query and fragment ignored)."""
    ref = ref.strip()
    m = re.search(r"/issues/(\d+)(?:[/?#]|$)", ref) or re.fullmatch(r"#?(\d+)", ref)
    if not m:
        sys.exit(f"tracker: {ref!r} is not an issue reference")
    return m.group(1)


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.exit(f"tracker: cannot read {path}: {exc}")


def issue_row(number_: int, title: str, labels: list[str], created_at: str) -> dict:
    return {"number": number_, "title": title, "labels": labels, "created_at": created_at}


def select(rows: list[dict], labels: list[str], title_prefix: str | None) -> list[dict]:
    """Keep rows carrying every label (case-insensitive) and the title prefix; oldest first."""
    want = {canonical(n) for n in labels if n.strip()}
    rows = [r for r in rows
            if want <= {canonical(n) for n in r["labels"]}
            and (not title_prefix or r["title"].startswith(title_prefix))]
    return sorted(rows, key=lambda r: (r["created_at"], r["number"]))


class GitHub:
    def list(self, state: str, labels: list[str]) -> list[dict]:
        cmd = ["gh", "issue", "list", "--state", state,
               "--json", "number,title,labels,createdAt", "--limit", "1000"]
        for name in labels:  # gh filters server-side first, so send what select() matches on
            cmd += ["--label", name.strip()]
        return [issue_row(i["number"], i["title"], [lb["name"] for lb in i["labels"]], i["createdAt"])
                for i in json.loads(sh(*cmd))]

    def get(self, n: str) -> str:
        return json.loads(sh("gh", "issue", "view", n, "--json", "body"))["body"]

    def put(self, n: str, body: str) -> None:
        sh("gh", "issue", "edit", n, "--body-file", "-", stdin=body)

    def create(self, title: str, body: str) -> str:
        url = sh("gh", "issue", "create", "--title", title, "--body-file", "-", stdin=body).strip()
        return number(url)

    def comment(self, n: str, body: str) -> None:
        sh("gh", "issue", "comment", n, "--body-file", "-", stdin=body)

    def labels(self, n: str) -> list[str]:
        return [lb["name"] for lb in json.loads(sh("gh", "issue", "view", n, "--json", "labels"))["labels"]]

    def label(self, n: str, add: list[str], remove: list[str]) -> None:
        add, remove = check_labels(add, remove)
        if remove:
            # gh fails on removing a label the issue lacks; Gitea skips it. Match
            # Gitea so a repeated cleanup is a no-op. Names are case-insensitive.
            current = {name.casefold(): name for name in self.labels(n)}
            remove = list(dict.fromkeys(
                current[name.casefold()] for name in remove if name.casefold() in current))
        if not add and not remove:
            return
        if add:
            # GitHub label names are case-insensitive
            known = {lb["name"].casefold()
                     for lb in json.loads(sh("gh", "label", "list", "--json", "name", "--limit", "1000"))}
            for name in add:
                if name.casefold() not in known:
                    sh("gh", "label", "create", name, "--color", NEW_LABEL_COLOR)
                    known.add(name.casefold())
        cmd = ["gh", "issue", "edit", n]
        for name in add:
            cmd += ["--add-label", name]
        for name in remove:
            cmd += ["--remove-label", name]
        sh(*cmd)

    def author(self, n: str) -> str:
        return json.loads(sh("gh", "issue", "view", n, "--json", "author"))["author"]["login"]


class Gitea:
    PAGE = 50

    def __init__(self, base: str, owner: str, repo: str):
        base = os.environ.get("GITEA_URL") or base
        self.root = f"{base.rstrip('/')}/api/v1"
        self.api = f"{self.root}/repos/{owner}/{repo}"
        self.token = os.environ.get("GITEA_TOKEN") or os.environ.get("TEA_TOKEN")
        if not self.token:
            sys.exit("tracker: set GITEA_TOKEN (or TEA_TOKEN) for Gitea")

    def request(self, method: str, path: str, payload: dict | None = None,
                *, repo: bool = True) -> dict | list:
        """One REST call under the repo (or, with repo=False, the API root, e.g. `/user`).
        Raises GiteaError, so a caller (ship-pr) can tell a 404 from an outage."""
        req = urllib.request.Request(
            (self.api if repo else self.root) + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": f"token {self.token}", "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace").strip()[:200]
            raise GiteaError(f"Gitea {method} {path} -> {exc.code} {exc.reason}"
                             + (f": {detail}" if detail else ""), exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise GiteaError(f"Gitea {method} {path} -> {exc}") from None

    def call(self, method: str, path: str, payload: dict | None = None) -> dict | list:
        try:
            return self.request(method, path, payload)
        except GiteaError as exc:
            sys.exit(f"tracker: {exc}")

    def list(self, state: str, labels: list[str]) -> list[dict]:
        rows: list[dict] = []
        for page in range(1, 1000):
            batch = self.call("GET", f"/issues?state={state}&type=issues&limit={self.PAGE}&page={page}") or []
            if not batch:  # a short page is not the end: the server may cap `limit`
                break
            rows += [issue_row(i["number"], i["title"], [lb["name"] for lb in i.get("labels") or []],
                               i["created_at"]) for i in batch]
        return rows

    def get(self, n: str) -> str:
        return self.call("GET", f"/issues/{n}").get("body") or ""

    def put(self, n: str, body: str) -> None:
        self.call("PATCH", f"/issues/{n}", {"body": body})

    def create(self, title: str, body: str) -> str:
        return str(self.call("POST", "/issues", {"title": title, "body": body})["number"])

    def comment(self, n: str, body: str) -> None:
        self.call("POST", f"/issues/{n}/comments", {"body": body})

    def labels(self, n: str) -> list[str]:
        return [lb["name"] for lb in self.call("GET", f"/issues/{n}/labels") or []]

    def repo_labels(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for page in range(1, 1000):
            batch = self.call("GET", f"/labels?limit=50&page={page}") or []
            if not batch:
                break
            found.update((lb["name"], lb["id"]) for lb in batch)
        return found

    def label(self, n: str, add: list[str], remove: list[str]) -> None:
        add, remove = check_labels(add, remove)
        ids = self.repo_labels()
        for name in add:
            if name not in ids:
                ids[name] = self.call("POST", "/labels", {"name": name, "color": f"#{NEW_LABEL_COLOR}"})["id"]
        if add:
            self.call("POST", f"/issues/{n}/labels", {"labels": [ids[name] for name in add]})
        for name in remove:
            if name in ids:  # a label the repo lacks cannot be on the issue
                self.call("DELETE", f"/issues/{n}/labels/{ids[name]}")

    def author(self, n: str) -> str:
        return self.call("GET", f"/issues/{n}")["user"]["login"]


def forge():
    kind = (os.environ.get("TRACKER") or "").strip().lower() or None
    if kind not in (None, "github", "gitea"):
        sys.exit(f"tracker: TRACKER must be github or gitea, not {os.environ['TRACKER']!r}")
    if kind == "github":  # gh finds the repo itself; no need to parse origin
        return GitHub()
    host, base, owner, repo = remote()
    if kind is None and host == "github.com":
        return GitHub()
    return Gitea(base, owner, repo)


def main() -> int:
    ap = argparse.ArgumentParser(description="Read and write Epic/story issue bodies (GitHub or Gitea).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("get"); p.add_argument("ref"); p.add_argument("-o", "--output")
    p = sub.add_parser("put"); p.add_argument("ref"); p.add_argument("file")
    p = sub.add_parser("create"); p.add_argument("--title", required=True); p.add_argument("--body-file", required=True)
    p.add_argument("--label", nargs="+", action="extend", default=[], metavar="NAME")
    p = sub.add_parser("comment"); p.add_argument("ref"); p.add_argument("--body", required=True)
    p = sub.add_parser("labels"); p.add_argument("ref")
    p = sub.add_parser("label"); p.add_argument("ref")
    p.add_argument("--add", nargs="+", action="extend", default=[], metavar="NAME")
    p.add_argument("--remove", nargs="+", action="extend", default=[], metavar="NAME")
    p = sub.add_parser("author"); p.add_argument("ref")
    p = sub.add_parser("list"); p.add_argument("--state", choices=("open", "closed", "all"), default="open")
    p.add_argument("--label", nargs="+", action="extend", default=[], metavar="NAME")
    p.add_argument("--title-prefix", metavar="TEXT")
    args = ap.parse_args()
    if args.cmd == "create" and args.label:  # refuse before an issue exists
        try:
            check_labels(args.label, [])
        except LabelRefused as exc:
            print(f"tracker: {exc}", file=sys.stderr)
            return 2
    if args.cmd == "label":  # validate before touching the forge, so a refusal changes nothing
        if not args.add and not args.remove:
            print("tracker: label needs --add or --remove", file=sys.stderr)
            return 2
        try:
            check_labels(args.add, args.remove)
        except LabelRefused as exc:
            print(f"tracker: {exc}", file=sys.stderr)
            return 2
    f = forge()
    if args.cmd == "get":
        body = f.get(number(args.ref))
        if args.output:
            try:
                Path(args.output).write_text(body, encoding="utf-8")
            except OSError as exc:
                sys.exit(f"tracker: cannot write {args.output}: {exc}")
            print(args.output)
        else:
            print(body)
    elif args.cmd == "put":
        f.put(number(args.ref), read(args.file))
        print(f"updated #{number(args.ref)}")
    elif args.cmd == "create":
        n = f.create(args.title, read(args.body_file))
        print("#" + n, flush=True)  # the issue exists now, even if labelling fails next
        if args.label:
            f.label(n, args.label, [])
    elif args.cmd == "comment":
        f.comment(number(args.ref), args.body)
        print(f"commented on #{number(args.ref)}")
    elif args.cmd == "labels":
        for name in f.labels(number(args.ref)):
            print(name)
    elif args.cmd == "label":
        f.label(number(args.ref), args.add, args.remove)
        print(f"labelled #{number(args.ref)}")
    elif args.cmd == "author":
        print(f.author(number(args.ref)))
    elif args.cmd == "list":
        print(json.dumps(select(f.list(args.state, args.label), args.label, args.title_prefix), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
