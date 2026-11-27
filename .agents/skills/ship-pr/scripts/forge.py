#!/usr/bin/env python3
"""The forge behind ship-pr: GitHub through `gh`, Gitea through its REST API.

  forge.py detect                                  print `github` or `gitea`
  forge.py find [--branch B]                       the open PR for B (default: this branch), as JSON;
                                                   exit 1 when there is none
  forge.py create --title T --body-file F [--base main] [--head B]
                                                   open a PR; print its number and url as JSON
  forge.py comment --pr N (--body TEXT | --body-file F)
  forge.py checks --pr N                           check counts on the head, as JSON
  forge.py reopen --pr N                           close and reopen (re-runs CI after a retarget)

The forge comes from the `origin` remote exactly as `.agents/scripts/tracker.py`
decides it (that file is imported, not copied): github.com is GitHub, any other
host is Gitea, `TRACKER=github|gitea` overrides. Gitea uses tracker.py's client,
so `GITEA_TOKEN` (or `TEA_TOKEN`) and `GITEA_URL` mean the same here. tracker.py
is the project's own copy (rendered with the harness); without it, only a
github.com origin works.

Exits 0 on success, 1 when `find` has no PR, 2 on a forge or setup error.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GH_TIMEOUT = 60
# A reply ship-pr posts carries this marker, so a later run (and the merge gate)
# can tie it to the finding even when the forge has no thread to put it in.
REPLY_MARKER = "<!-- ship-pr:reply {id} -->"
GITEA_PAGE = 50
REVIEW_STATES = ("APPROVED", "REQUEST_CHANGES")  # what decides a Gitea reviewer's verdict

THREADS_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          first: comments(first: 1) { nodes { author { login } body } }
          latest: comments(last: 1) { nodes { author { login } body } }
        }
      }
    }
  }
}
"""
REPLY_MUTATION = """
mutation($thread: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) {
    comment { id }
  }
}
"""
RESOLVE_MUTATION = """
mutation($thread: ID!) {
  resolveReviewThread(input: {threadId: $thread}) { thread { isResolved } }
}
"""


class ForgeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def tracker_module(here: Path | None = None):
    """`.agents/scripts/tracker.py` from the nearest ancestor that has one (the
    project root when rendered, the genesis root when run from templates/). Never
    a copy in the user's home: the pipeline ships in each repo."""
    here = (here or Path(__file__)).resolve()
    candidates = [parent / ".agents" / "scripts" / "tracker.py" for parent in here.parents]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("ship_pr_tracker", path)
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return module
    return None


def origin_url() -> str:
    try:
        run = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ForgeError(f"cannot read the origin remote: {exc}") from None
    if run.returncode != 0:
        raise ForgeError("no `origin` remote")
    return run.stdout.strip()


def detect(tracker=None) -> str:
    """`github` or `gitea`, by tracker.py's rule."""
    override = (os.environ.get("TRACKER") or "").strip().lower()
    if override in ("github", "gitea"):
        return override
    if override:
        raise ForgeError(f"TRACKER must be github or gitea, not {override!r}")
    tracker = tracker or tracker_module()
    try:
        url = origin_url()
    except ForgeError:  # no origin: leave it to gh, as before Gitea support (GH_REPO still works)
        return "github"
    if tracker is None:  # without tracker.py only GitHub works; never send gh at another host
        if re.search(r"(^|[@/.])github\.com[:/]", url):
            return "github"
        raise ForgeError(f"origin {url} is not GitHub and no tracker.py was found: "
                         "re-render the harness or install the genesis pipeline")
    try:
        host = tracker.parse_remote(url)[0]
    except SystemExit as exc:  # tracker.py reports a bad remote by exiting
        raise ForgeError(str(exc.code)) from None
    return "github" if host == "github.com" else "gitea"


def connect():
    """The forge client for this repository."""
    tracker = tracker_module()
    if detect(tracker) == "github":
        return GitHub()
    if tracker is None:
        raise ForgeError("TRACKER=gitea needs .agents/scripts/tracker.py (re-render the harness)")
    return Gitea.from_tracker(tracker)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def severity(body: str) -> str:
    """`important`, `nit` or `unlabelled` from the reviewer's `Important —` / `Nit —` prefix.
    The merge gate treats anything that is not a Nit as Important."""
    head = re.sub(r"^[\s*_>#`]+", "", body or "").lower()
    if head.startswith("nit"):
        return "nit"
    if head.startswith("important"):
        return "important"
    return "unlabelled"


def references(body: str, comment_id) -> bool:
    """Does a comment name this finding: ship-pr's marker, `comment <id>` / `inline #<id>`,
    or its URL anchor?"""
    return bool(re.search(rf"(?:ship-pr:reply\s+|\b(?:comment|inline)\s+#?|issuecomment-|#discussion_r)"
                          rf"{comment_id}\b", body or ""))


# ── GitHub ────────────────────────────────────────────────────────────────


class GitHub:
    kind = "github"

    def run(self, *args: str, stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True,
                                  timeout=GH_TIMEOUT)
        except FileNotFoundError:
            raise ForgeError("gh CLI not found") from None
        except subprocess.TimeoutExpired:
            raise ForgeError(f"gh {' '.join(args[:2])} timed out") from None
        if check and proc.returncode != 0:
            raise ForgeError(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip()[:300]}")
        return proc

    def json(self, *args: str, check: bool = True):
        out = self.run(*args, check=check).stdout
        try:
            return json.loads(out) if out.strip() else None
        except json.JSONDecodeError:
            raise ForgeError(f"gh {' '.join(args[:2])} printed no JSON") from None

    def find(self, branch: str | None = None) -> dict | None:
        proc = self.run("pr", "view", *([branch] if branch else []), "--json", "number,url,state",
                        check=False)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)

    def create(self, title: str, body: str, base: str, head: str | None) -> dict:
        args = ["pr", "create", "--base", base, "--title", title, "--body-file", "-"]
        url = self.run(*args, *(["--head", head] if head else []), stdin=body).stdout.strip().splitlines()[-1]
        return {"number": int(url.rstrip("/").rsplit("/", 1)[1]), "url": url}

    def comment(self, pr: str, body: str) -> None:
        self.run("pr", "comment", str(pr), "--body-file", "-", stdin=body)

    def repo(self) -> tuple[str, str]:
        name = self.run("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").stdout.strip()
        owner, repo = name.split("/", 1)
        return owner, repo

    def threads(self, pr: str) -> list[dict]:
        """Every review thread, with GitHub's own resolved/outdated flags."""
        owner, repo = self.repo()
        nodes: list[dict] = []
        cursor = None
        while True:  # the merge gate reads this list as complete, so follow every page
            data = self.json("api", "graphql", "-f", f"query={THREADS_QUERY}",
                             "-F", f"owner={owner}", "-F", f"repo={repo}", "-F", f"pr={pr}",
                             *(["-f", f"cursor={cursor}"] if cursor else []))
            page = data["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes += page["nodes"]
            info = page.get("pageInfo") or {}
            if not (info.get("hasNextPage") and info.get("endCursor")):
                break
            if info["endCursor"] == cursor:  # a stuck cursor would loop forever; the list is incomplete
                raise ForgeError(f"GitHub review threads for PR {pr}: the page cursor did not advance")
            cursor = info["endCursor"]
        out = []
        for node in nodes:
            first = (node["first"]["nodes"] or [{}])[0]
            last = (node["latest"]["nodes"] or [{}])[-1]
            out.append({
                "id": node["id"], "path": node["path"] or "", "line": node["line"],
                "author": (last.get("author") or {}).get("login", ""), "body": last.get("body", ""),
                "severity": severity(first.get("body", "")),
                "resolved": node["isResolved"], "outdated": node["isOutdated"],
                # GitHub resolves threads, so only a resolved or outdated one is handled.
                "answered": node["isResolved"] or node["isOutdated"],
            })
        return out

    def reply(self, pr: str, thread: str, body: str) -> dict:
        self.run("api", "graphql", "-f", f"query={REPLY_MUTATION}", "-F", f"thread={thread}",
                 "-F", f"body={body}")
        return {"thread": thread, "via": "thread"}

    def resolve(self, thread: str) -> bool:
        self.run("api", "graphql", "-f", f"query={RESOLVE_MUTATION}", "-F", f"thread={thread}")
        return True

    def checks(self, pr: str, required: bool = False) -> list[dict]:
        """[{name, bucket}] for the head; with `required`, only the required checks
        (all of them when the repo marks none required)."""
        if required:
            proc = self.run("pr", "checks", str(pr), "--required", "--json", "name,bucket", check=False)
            if proc.stdout.strip():  # gh exits non-zero for pending/failing checks; the JSON stands
                return json.loads(proc.stdout)
        proc = self.run("pr", "checks", str(pr), "--json", "name,bucket", check=False)
        return json.loads(proc.stdout) if proc.stdout.strip() else []

    def view(self, pr: str) -> dict:
        """The fields the merge gate reads, in one shape for both forges."""
        data = self.json("pr", "view", str(pr), "--json",
                         "number,url,state,isDraft,mergeStateStatus,reviewDecision,"
                         "headRefName,headRefOid,baseRefName,labels,author")
        return {
            "number": data["number"], "url": data["url"], "state": data["state"],
            "draft": bool(data.get("isDraft")), "head": data["headRefName"], "sha": data["headRefOid"],
            "base": data["baseRefName"], "author": (data.get("author") or {}).get("login", ""),
            "labels": [lb["name"] for lb in data.get("labels") or []],
            "changes_requested": (data.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED",
            "merge_state": (data.get("mergeStateStatus") or "UNKNOWN").upper(),
        }

    def files(self, pr: str) -> list[str]:
        out = self.run("api", f"repos/{{owner}}/{{repo}}/pulls/{pr}/files", "--paginate",
                       "--jq", ".[].filename").stdout
        return [line for line in out.splitlines() if line]

    def dependents(self, head: str) -> list[int]:
        return [int(n) for n in (self.json("pr", "list", "--base", head, "--json", "number",
                                           "-q", "[.[].number]") or [])]

    def retarget(self, pr: int, base: str) -> None:
        self.run("pr", "edit", str(pr), "--base", base)

    def reopen(self, pr: str) -> None:
        self.run("pr", "close", str(pr))
        self.run("pr", "reopen", str(pr))

    def merge(self, pr: str, method: str, sha: str, delete_branch: bool = True) -> str:
        self.run("pr", "merge", str(pr), f"--{method}", *(["--delete-branch"] if delete_branch else []),
                 "--match-head-commit", sha)
        data = self.json("pr", "view", str(pr), "--json", "mergeCommit", check=False) or {}
        return ((data.get("mergeCommit") or {}).get("oid")) or ""


# ── Gitea ─────────────────────────────────────────────────────────────────


def gitea_bucket(state: str) -> str:
    return {"success": "pass", "warning": "pass", "pending": "pending", "skipped": "skipping",
            "failure": "fail", "error": "fail"}.get((state or "").lower(), "pending")


def protection_for(rules: list[dict], branch: str) -> dict | None:
    """The branch protection rule Gitea applies to `branch`: a plain rule name
    matches case-insensitively, a glob as a glob; the lowest priority wins."""
    def matches(rule: dict) -> bool:
        name = rule.get("rule_name") or rule.get("branch_name") or ""
        if any(ch in name for ch in "*?["):
            return fnmatch.fnmatchcase(branch, name)
        return name.casefold() == branch.casefold()
    hits = [r for r in rules if matches(r)]
    return sorted(hits, key=lambda r: r.get("priority") or 0)[0] if hits else None


class Gitea:
    kind = "gitea"

    def __init__(self, client, error_type):
        self.client = client
        self.error_type = error_type
        self._me: str | None = None

    @classmethod
    def from_tracker(cls, tracker) -> "Gitea":
        try:
            _host, base, owner, repo = tracker.parse_remote(origin_url())
            client = tracker.Gitea(base, owner, repo)  # GITEA_URL, GITEA_TOKEN / TEA_TOKEN
        except SystemExit as exc:
            raise ForgeError(str(exc.code).removeprefix("tracker: ")) from None
        return cls(client, tracker.GiteaError)

    def call(self, method: str, path: str, payload: dict | None = None, *, repo: bool = True):
        try:
            return self.client.request(method, path, payload, repo=repo)
        except self.error_type as exc:
            raise ForgeError(str(exc), getattr(exc, "status", None)) from None

    def pages(self, path: str) -> list:
        """Every item of a paginated list. Stops on an empty page, or on a page
        that repeats the last one (an endpoint that ignores `page`)."""
        sep = "&" if "?" in path else "?"
        items: list = []
        previous = None
        for page in range(1, 1000):
            batch = self.call("GET", f"{path}{sep}limit={GITEA_PAGE}&page={page}") or []
            if not batch or batch == previous:
                break
            items += batch
            previous = batch
        return items

    def me(self) -> str:
        """The token's own login ("" when unreadable), cached."""
        if self._me is None:
            try:
                self._me = (self.call("GET", "/user", repo=False) or {}).get("login") or ""
            except ForgeError:
                self._me = ""
        return self._me

    # PRs
    def pull(self, pr) -> dict:
        return self.call("GET", f"/pulls/{pr}")

    def find(self, branch: str | None = None) -> dict | None:
        branch = branch or current_branch()
        for pull in self.pages("/pulls?state=open"):
            if (pull.get("head") or {}).get("ref") == branch:
                return {"number": pull["number"], "url": pull["html_url"], "state": "OPEN"}
        return None

    def create(self, title: str, body: str, base: str, head: str | None) -> dict:
        pull = self.call("POST", "/pulls", {"title": title, "body": body, "base": base,
                                            "head": head or current_branch()})
        return {"number": pull["number"], "url": pull["html_url"]}

    def comment(self, pr, body: str) -> None:
        self.call("POST", f"/issues/{pr}/comments", {"body": body})

    def statuses(self, sha: str) -> list[dict]:
        """The latest status per context on a commit (Gitea's combined status)."""
        out: list[dict] = []
        previous = None
        for page in range(1, 100):
            data = self.call("GET", f"/commits/{sha}/status?limit={GITEA_PAGE}&page={page}") or {}
            batch = data.get("statuses") or []
            if not batch or batch == previous:
                break
            out += batch
            previous = batch
            if len(out) >= (data.get("total_count") or 0):
                break
        return out

    def protection(self, branch: str) -> dict | None:
        """None when the branch is unprotected, or the token can't read the rules
        (they need repo admin): the gate then requires every status to pass."""
        try:
            rules = self.call("GET", "/branch_protections") or []
        except ForgeError as exc:
            if exc.status in (403, 404):
                return None
            raise
        return protection_for(rules, branch)

    def checks(self, pr, required: bool = False) -> list[dict]:
        pull = self.pull(pr)
        statuses = self.statuses(pull["head"]["sha"])
        rows = [{"name": s.get("context") or "", "bucket": gitea_bucket(s.get("status"))} for s in statuses]
        if not required:
            return rows
        rule = self.protection(pull["base"]["ref"])
        contexts = (rule or {}).get("status_check_contexts") or []
        if not (rule and rule.get("enable_status_check") and contexts):
            return rows
        out = []
        for pattern in contexts:  # Gitea matches required contexts as globs
            hits = [r for r in rows if fnmatch.fnmatchcase(r["name"], pattern)]
            out += hits or [{"name": pattern, "bucket": "pending"}]  # required, not reported yet
        return out

    def reviews(self, pr) -> list[dict]:
        return self.pages(f"/pulls/{pr}/reviews")

    def decision(self, reviews: list[dict], rule: dict | None, head_sha: str) -> str:
        """GitHub's reviewDecision, from each reviewer's latest approve/reject."""
        latest: dict[str, dict] = {}
        for review in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
            if review.get("state") in REVIEW_STATES and not review.get("dismissed"):
                latest[((review.get("user") or {}).get("login") or "").lower()] = review
        if any(r["state"] == "REQUEST_CHANGES" for r in latest.values()):
            return "CHANGES_REQUESTED"
        stale_ok = not (rule or {}).get("dismiss_stale_approvals")
        approvals = sum(1 for r in latest.values() if r["state"] == "APPROVED"
                        and (stale_ok or r.get("commit_id") == head_sha))
        needed = int((rule or {}).get("required_approvals") or 0)
        if approvals and approvals >= needed:
            return "APPROVED"
        return "REVIEW_REQUIRED" if needed else ""

    def merge_state(self, pull: dict, rule: dict | None, decision: str) -> str:
        if pull.get("mergeable") is False:
            return "DIRTY"
        if (rule or {}).get("block_on_outdated_branch") and pull.get("merge_base") \
                and pull["merge_base"] != (pull.get("base") or {}).get("sha"):
            return "BEHIND"
        if decision == "REVIEW_REQUIRED":
            return "BLOCKED"
        return "CLEAN"

    def view(self, pr) -> dict:
        pull = self.pull(pr)
        rule = self.protection(pull["base"]["ref"])
        decision = self.decision(self.reviews(pr), rule, pull["head"]["sha"])
        return {
            "number": pull["number"], "url": pull["html_url"], "state": pr_state(pull),
            "draft": bool(pull.get("draft")), "head": pull["head"]["ref"], "sha": pull["head"]["sha"],
            "base": pull["base"]["ref"], "author": (pull.get("user") or {}).get("login", ""),
            "labels": [lb["name"] for lb in pull.get("labels") or []],
            "changes_requested": decision == "CHANGES_REQUESTED",
            "merge_state": self.merge_state(pull, rule, decision),
        }

    def gh_view(self, pr) -> tuple[dict, dict]:
        """The PR in the shape `gh pr view --json` gives watch_pr.py, plus the
        check counts `gh pr checks` would, so the watcher judges both forges alike."""
        pull = self.pull(pr)
        sha = pull["head"]["sha"]
        rule = self.protection(pull["base"]["ref"])
        reviews = self.reviews(pr)
        decision = self.decision(reviews, rule, sha)
        statuses = self.statuses(sha)
        commits = self.pages(f"/pulls/{pr}/commits")
        head = [c for c in commits if c.get("sha") == sha] or commits
        dates = sorted(filter(None, (parse_time(((c.get("commit") or {}).get("committer") or {}).get("date"))
                                     for c in head)))
        view = {
            "number": pull["number"], "url": pull["html_url"], "state": pr_state(pull),
            "isDraft": bool(pull.get("draft")), "reviewDecision": decision,
            "mergeStateStatus": self.merge_state(pull, rule, decision),
            "statusCheckRollup": statuses,
            "reviews": [{"author": {"login": (r.get("user") or {}).get("login", "")},
                         "state": r.get("state"), "submittedAt": r.get("submitted_at")}
                        for r in reviews if r.get("state") != "PENDING"],
            "comments": [{"author": {"login": (c.get("user") or {}).get("login", "")},
                          "createdAt": c.get("created_at"), "updatedAt": c.get("updated_at"),
                          "url": c.get("html_url")} for c in self.issue_comments(pr)],
            "commits": [{"committedDate": dates[-1].isoformat()}] if dates else [],
            "labels": [{"name": lb["name"]} for lb in pull.get("labels") or []],
        }
        counts = {"pass": 0, "pending": 0, "fail": 0, "skipping": 0, "cancel": 0}
        for status in statuses:
            counts[gitea_bucket(status.get("status"))] += 1
        counts["total"] = len(statuses)
        return view, counts

    def issue_comments(self, pr) -> list[dict]:
        return self.call("GET", f"/issues/{pr}/comments") or []

    def threads(self, pr) -> list[dict]:
        """Every inline finding, with whether it counts as answered.

        Gitea has no GraphQL, and resolving is optional there, so a finding is
        answered when it is resolved, when the PR's author or the token's user
        replied to it (in its thread, or in a PR comment naming its id), or when
        a commit landed after the review that raised it."""
        pull = self.pull(pr)
        head_sha = pull["head"]["sha"]
        repliers = {(pull.get("user") or {}).get("login", "").lower(), self.me().lower()}
        repliers |= {n.strip().lower() for n in os.environ.get("SHIP_PR_REPLIERS", "").split(",")}
        repliers.discard("")
        comments = []
        for review in self.reviews(pr):
            if review.get("state") == "PENDING":
                continue
            for c in self.call("GET", f"/pulls/{pr}/reviews/{review['id']}/comments") or []:
                comments.append((review, c))
        comments.sort(key=lambda rc: (rc[1].get("created_at") or "", rc[1]["id"]))
        roots: dict[tuple, tuple] = {}
        replies: dict[tuple, list] = {}
        for review, c in comments:
            key = (c.get("path") or "", c.get("position") or c.get("original_position") or 0)
            if key not in roots:
                roots[key] = (review, c)
            else:
                replies.setdefault(key, []).append(c)
        notes = self.issue_comments(pr)
        out = []
        for key, (review, root) in roots.items():
            root_author = ((root.get("user") or {}).get("login") or "").lower()
            created = root.get("created_at") or ""

            def replied(c: dict) -> bool:
                who = ((c.get("user") or {}).get("login") or "").lower()
                return (who in repliers and (c.get("created_at") or "") >= created
                        and (who != root_author or references(c.get("body", ""), root["id"])))

            thread = replies.get(key, [])
            if root.get("resolver"):
                how = "resolved"
            elif any(replied(c) for c in thread) or any(
                    replied(n) and references(n.get("body", ""), root["id"]) for n in notes):
                how = "replied"
            elif review.get("stale") or (review.get("commit_id") and review["commit_id"] != head_sha):
                how = "commit"
            else:
                how = ""
            last = thread[-1] if thread else root
            out.append({
                "id": root["id"], "path": root.get("path") or "",
                "line": root.get("position") or root.get("original_position"),
                "author": (last.get("user") or {}).get("login", ""), "body": last.get("body", ""),
                "severity": severity(root.get("body", "")), "resolved": bool(root.get("resolver")),
                "outdated": how == "commit", "answered": bool(how), "answered_by": how or None,
            })
        return out

    def reply(self, pr, comment_id, body: str) -> dict:
        body = f"{body}\n\n{REPLY_MARKER.format(id=comment_id)}"
        try:
            made = self.call("POST", f"/pulls/{pr}/comments/{comment_id}/replies", {"body": body})
            return {"thread": comment_id, "via": "thread", "id": (made or {}).get("id")}
        except ForgeError as exc:
            if exc.status not in (404, 405):
                raise
        # An older Gitea has no reply endpoint: answer in the PR conversation.
        made = self.call("POST", f"/issues/{pr}/comments",
                         {"body": f"> On review comment {comment_id}\n\n{body}"})
        return {"thread": comment_id, "via": "comment", "id": (made or {}).get("id")}

    def resolve(self, comment_id) -> bool:
        try:
            self.call("POST", f"/pulls/comments/{comment_id}/resolve")
            return True
        except ForgeError as exc:
            if exc.status in (404, 405):
                return False  # no resolve endpoint: the reply marker still answers it
            raise

    def files(self, pr) -> list[str]:
        return [f["filename"] for f in self.pages(f"/pulls/{pr}/files")]

    def dependents(self, head: str) -> list[int]:
        return [p["number"] for p in self.pages(f"/pulls?state=open&base_branch={head}")
                if (p.get("base") or {}).get("ref") == head]

    def retarget(self, pr: int, base: str) -> None:
        self.call("PATCH", f"/pulls/{pr}", {"base": base})

    def reopen(self, pr) -> None:
        self.call("PATCH", f"/pulls/{pr}", {"state": "closed"})
        self.call("PATCH", f"/pulls/{pr}", {"state": "open"})

    def merge(self, pr, method: str, sha: str, delete_branch: bool = True) -> str:
        self.call("POST", f"/pulls/{pr}/merge", {"Do": method, "head_commit_id": sha,
                                                 "delete_branch_after_merge": delete_branch})
        return self.pull(pr).get("merge_commit_sha") or ""


def pr_state(pull: dict) -> str:
    if pull.get("merged"):
        return "MERGED"
    return "OPEN" if pull.get("state") == "open" else "CLOSED"


def current_branch() -> str:
    run = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    branch = run.stdout.strip()
    if run.returncode != 0 or not branch or branch == "HEAD":
        raise ForgeError("not on a branch")
    return branch


def read_body(args) -> str:
    if getattr(args, "body_file", None):
        try:
            return Path(args.body_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ForgeError(f"cannot read {args.body_file}: {exc}") from None
    return args.body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect")
    p = sub.add_parser("find"); p.add_argument("--branch")
    p = sub.add_parser("create"); p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True); p.add_argument("--base", default="main"); p.add_argument("--head")
    p = sub.add_parser("comment"); p.add_argument("--pr", required=True)
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--body"); g.add_argument("--body-file")
    p = sub.add_parser("checks"); p.add_argument("--pr", required=True)
    p.add_argument("--required", action="store_true", help="only the checks branch protection requires")
    p = sub.add_parser("reopen"); p.add_argument("--pr", required=True)
    args = ap.parse_args()
    try:
        if args.cmd == "detect":
            print(detect())
            return 0
        forge = connect()
        if args.cmd == "find":
            found = forge.find(args.branch)
            if not found:
                print("no open pull request for this branch", file=sys.stderr)
                return 1
            print(json.dumps(found))
        elif args.cmd == "create":
            print(json.dumps(forge.create(args.title, read_body(args), args.base, args.head)))
        elif args.cmd == "comment":
            forge.comment(args.pr, read_body(args))
            print(f"commented on #{args.pr}")
        elif args.cmd == "checks":
            rows = forge.checks(args.pr, required=args.required)
            counts = {b: sum(1 for r in rows if r["bucket"] == b)
                      for b in ("pass", "pending", "fail", "skipping", "cancel")}
            print(json.dumps({**counts, "total": len(rows), "checks": rows}, indent=2))
        elif args.cmd == "reopen":
            forge.reopen(args.pr)
            print(f"reopened #{args.pr}")
    except ForgeError as exc:
        print(f"forge: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
