#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""The mechanical half of wave-dispatcher: git, plans and status, no judgment.

  dispatch.py load (--epic REF | --story REF... | --files FILE...) [--base REF]
  dispatch.py prepare [--max N] [--plan] [--allow-dirty] [--baseline-timeout S]
  dispatch.py check UNIT [--timeout SEC]
  dispatch.py retry UNIT --note TEXT [--review-findings FILE]
  dispatch.py merge UNIT [--human]
  dispatch.py block UNIT --note TEXT
  dispatch.py learn --unit UNIT --paths GLOB... --constraint TEXT
  dispatch.py escalate UNIT --diagnosis FILE --outcome attempt|replan|needs-input
                       [--question TEXT] [--lesson-paths GLOB... --lesson TEXT]
  dispatch.py integrate STORY [--sync REF] [--push]
  dispatch.py report

UNIT is `<story>/<track>` (e.g. S1/A). Every command prints JSON on stdout and
exits 0 on success, 1 when the unit failed a check (the JSON says why), 2 on a
usage or environment error.

State lives in `<git common dir>/agent-plan/`: a copy of each plan body, a
brief per prepared unit, and state.json recording where each body came from.
Every status change is written back to its source — the GitHub/Gitea issue via
tracker.py, or the original file for `--files`.

Trust: `check` and `integrate` run each plan's verify commands with `bash -c`
in the worktree. A plan loaded from an issue can be changed by anyone with
write access to that issue, so load only from trackers whose writers you
trust, and read new or changed verify commands before dispatching.

Layout, for a story whose plan says `branch: feat/41-x`:
  feat/41-x                    the story's integration branch (from the base, plus
                               the branches of the stories it depends on)
  feat/41-x--<track>           one branch per track
  <repo>-tracks/S1-integration and <repo>-tracks/S1-<track>   their worktrees
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    import yaml  # noqa: F401  (plan.py needs it; re-run this script, not plan.py, under uv)
except ImportError:
    if shutil.which("uv") and not os.environ.get("AGENT_PLAN_REEXEC"):
        os.environ["AGENT_PLAN_REEXEC"] = "1"
        os.execvp("uv", ["uv", "run", "--quiet", "--script", __file__, *sys.argv[1:]])
    sys.exit("dispatch.py needs PyYAML: install it, or install uv so it can fetch it")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


plan = _load("plan")


class DispatchError(Exception):
    pass


# ── git ──────────────────────────────────────────────────────────────────────

def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    run = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and run.returncode != 0:
        raise DispatchError(f"git {' '.join(args)}: {run.stderr.strip() or run.stdout.strip()}")
    return run.stdout.strip()


def ok(*args: str, cwd: Path | str | None = None) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel"))


def work_dir() -> Path:
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (Path.cwd() / common).resolve()
    return common / "agent-plan"


def default_base() -> str:
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if head:
        return head
    for name in ("main", "master"):
        if ok("show-ref", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return git("rev-parse", "--abbrev-ref", "HEAD")


# ── state ────────────────────────────────────────────────────────────────────

class State:
    def __init__(self) -> None:
        self.root = repo_root()
        self.work = work_dir()
        self.path = self.work / "state.json"
        try:
            self.data = json.loads(self.path.read_text()) if self.path.is_file() else {}
        except json.JSONDecodeError as exc:
            raise DispatchError(f"{self.path} is corrupt ({exc}); run dispatch.py load again") from exc

    def save(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    @property
    def trees(self) -> Path:
        return Path(self.data.get("trees") or self.root.parent / f"{self.root.name}-tracks")

    @property
    def base(self) -> str:
        return self.data.get("base") or default_base()

    def files(self) -> list[str]:
        return [str(self.work / f) for f in sorted(self.data.get("sources", {}))]

    def plans(self):
        if not self.data.get("sources"):
            raise DispatchError("nothing loaded; run dispatch.py load first")
        return plan.load(self.files())

    def story_file(self, sid: str) -> Path:
        name = f"story-{sid}.md"
        if name not in self.data.get("sources", {}):
            raise DispatchError(f"story {sid} is not loaded")
        return self.work / name

    def story(self, sid: str) -> dict:
        return plan.extract(self.story_file(sid).read_text(encoding="utf-8"), f"story {sid}")

    def publish(self, name: str) -> None:
        """Write a body back where it came from."""
        src = self.data["sources"][name]
        body = self.work / name
        if src["kind"] == "file":
            shutil.copyfile(body, src["path"])
        elif src["kind"] == "tracker":
            tracker = _load("tracker")
            tracker.forge().put(tracker.number(src["ref"]), body.read_text(encoding="utf-8"))

    def set_status(self, sid: str, track: str, status: str, note: str | None = None) -> None:
        f = self.story_file(sid)
        f.write_text(plan.set_status(f.read_text(encoding="utf-8"), track, status, note), encoding="utf-8")
        self.publish(f.name)


def record(st: State, unit: str, event: str, **fields) -> None:
    """Append to a unit's history. Unlike retry state, history is never
    forgotten: it outlives merges, restarts and reloads of the plans."""
    st.data.setdefault("history", {}).setdefault(unit, []).append({
        "event": event, "attempt": st.data.get("attempts", {}).get(unit, 1),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), **fields})


def summarize(events: list[dict]) -> dict:
    """Roll a unit's history up into the numbers a reviewer weighs."""
    def count(name: str) -> int:
        return sum(1 for e in events if e["event"] == name)
    checks = [e for e in events if e["event"] == "check"]
    ends = [e["event"] for e in events if e["event"] in ("merge", "conflict", "replan")]
    return {"starts": count("prepare"), "attempts": max((e["attempt"] for e in events), default=0),
            "checks": len(checks), "failed_checks": sum(1 for e in checks if not e["ok"]),
            "blocks": count("block"), "escalations": count("escalate"),
            # A restart throws away earlier attempts; a conflict throws away the merge.
            "rollbacks": sum(1 for e in events if e["event"] == "prepare" and e.get("restart"))
            + count("conflict"),
            "outcome": ends[-1] if ends else None}


def split_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise DispatchError(f"unit must be <story>/<track>, got {unit!r}")
    sid, track = unit.split("/", 1)
    return sid, track


def track_of(story: dict, track: str) -> dict:
    t = next((x for x in plan.as_list(story.get("tracks")) if str(x.get("id")) == track), None)
    if t is None:
        raise DispatchError(f"story {plan.story_key(story)} has no track {track}")
    return t


def story_branch(story: dict) -> str:
    branch = story.get("branch")
    if not branch or "<" in str(branch):
        raise DispatchError(f"story {plan.story_key(story)} has no branch in its plan")
    return str(branch)


def run_shell(command: str, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run a verify command. On timeout the whole process group is killed, so
    nothing it started keeps writing into the worktree after the cleanup."""
    proc = subprocess.Popen(["bash", "-c", command], cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return False, f"timed out after {timeout}s"
    tail = "\n".join((out or "").strip().splitlines()[-30:])
    return proc.returncode == 0, tail


# A test path: a `test`/`tests`/`__tests__`/`spec` directory, optionally with a
# `name_`/`name-` prefix (Rust crates keep in-tree tests in `src/contract_tests/`);
# a `test_*` file; or a `*_test(s).*`, `*-test(s).*`, `*.test.*` or `*.spec.*` file.
TEST_FILE = re.compile(
    r"(^|/)([\w.-]*[_-])?(tests?|__tests__|spec)/|(^|/)test_[^/]*$"
    r"|[_-]tests?\.[^/]+$|\.(test|spec)\.[^/]+$"
)

HUMAN_BRIEF = """

## Merge needs a human
This track is in the irreversible lane: it owns paths where a bad merge can't
simply be reverted (migrations, deploys, infrastructure). Your work merges only
after a person approves it, so say plainly in your report what it changes and
how to undo it.
"""

WEAK_BRIEF = """

## Your check already passes
`{verify}` passes before you have changed anything, so on its own it cannot
show that your work is right. Write a failing test for the acceptance
criteria first (red), then make it pass (green). `check` rejects this track
if the diff adds or changes no test file.
"""


def baseline(st: "State", unit: str, verify: str, tree: Path, timeout: int) -> bool:
    """Whether `verify` already passes on the untouched worktree, run once per unit."""
    seen = st.data.setdefault("baselines", {})
    if unit not in seen:
        passed, _ = run_shell(verify, tree, timeout)
        restore(tree)
        seen[unit] = passed
        st.save()
    return bool(seen[unit])


def weak_check(st: "State", unit: str, t: dict) -> bool:
    """A verify that passed before any work, on a track that isn't a declared refactor."""
    return bool(st.data.get("baselines", {}).get(unit)) and t.get("verify_baseline") != "pass"


def clean_tree(cwd: Path, ignore: tuple[str, ...] = ()) -> list[str]:
    return [line[3:] for line in git("status", "--porcelain", cwd=cwd).splitlines()
            if line.strip() and line[3:] not in ignore]


def restore(cwd: Path) -> None:
    """Undo what a verify run wrote (caches, regenerated lockfiles) so the
    worktree shows only the agent's commits. Only called on a tree that was
    clean before the run, so nothing of the agent's is lost."""
    git("checkout", "--", ".", cwd=cwd, check=False)
    git("clean", "-fdq", cwd=cwd, check=False)


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_load(st: State, args) -> dict:
    # Read every source before touching the loaded state, so a failed load
    # leaves the previous one intact.
    sources: dict[str, dict] = {}
    bodies: dict[str, str] = {}

    def take(text: str, src: dict) -> str:
        p = plan.extract(text, src.get("ref") or src.get("path", "input"))
        name = "epic.md" if p.get("kind") == "epic" else f"story-{plan.story_key(p)}.md"
        bodies[name] = text
        sources[name] = src
        return name

    if args.files:
        for f in args.files:
            try:
                text = Path(f).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise DispatchError(f"cannot read {f}: {exc}") from exc
            take(text, {"kind": "file", "path": str(Path(f).resolve())})
    else:
        tracker = _load("tracker")
        forge = tracker.forge()
        refs = list(args.story or [])
        if args.epic:
            name = take(forge.get(tracker.number(args.epic)), {"kind": "tracker", "ref": args.epic})
            epic = plan.extract(bodies[name])
            refs += [str(s.get("issue")) for s in plan.as_list(epic.get("stories"))
                     if plan.issue_number(s.get("issue"))]
        for ref in refs:
            take(forge.get(tracker.number(ref)), {"kind": "tracker", "ref": ref})
    st.work.mkdir(parents=True, exist_ok=True)
    for old in st.work.glob("*.md"):
        old.unlink()
    for name, text in bodies.items():
        (st.work / name).write_text(text, encoding="utf-8")
    st.data = {"sources": sources, "base": args.base or default_base(),
               "trees": str(st.root.parent / f"{st.root.name}-tracks"),
               "history": st.data.get("history", {})}  # a reload after replanning keeps the record
    st.save()
    epic, stories = st.plans()
    errs = plan.validate_set(epic, stories)
    planned = {plan.story_key(s) for s in stories}
    unplanned = [str(s.get("id")) for s in plan.as_list((epic or {}).get("stories")) if str(s.get("id")) not in planned]
    return {"ok": not errs, "loaded": sorted(sources), "unplanned_stories": unplanned,
            "errors": errs, "base": st.base, "trees": str(st.trees)}


def ensure_story_branch(st: State, story: dict, stories: dict[str, dict], dry: list | None) -> Path:
    branch = story_branch(story)
    sid = plan.story_key(story)
    integ = st.trees / f"{sid}-integration"
    if dry is not None:
        exists = ok("show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
        if not exists:
            dry.append(f"git branch {branch} {st.base}")
        if not integ.exists():
            dry.append(f"git worktree add {integ} {branch}")
        for up in map(str, plan.as_list(story.get("depends_on"))):
            upstream = stories.get(up)
            if upstream is None:
                continue
            up_branch = story_branch(upstream)
            if not ok("show-ref", "--verify", "--quiet", f"refs/heads/{up_branch}"):
                continue
            if exists and ok("merge-base", "--is-ancestor", up_branch, branch):
                continue
            dry.append(f"git -C {integ} merge --no-ff {up_branch}")
        return integ
    if not ok("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"):
        git("branch", branch, st.base)
    if not integ.exists():
        git("worktree", "add", str(integ), branch)
    # A story starts from the finished work of the stories it depends on.
    for up in map(str, plan.as_list(story.get("depends_on"))):
        upstream = stories.get(up)
        if upstream is None:
            raise DispatchError(f"story {sid} depends on {up}, which has no plan loaded")
        up_branch = story_branch(upstream)
        if not ok("show-ref", "--verify", "--quiet", f"refs/heads/{up_branch}"):
            continue  # already merged and deleted
        if ok("merge-base", "--is-ancestor", up_branch, "HEAD", cwd=integ):
            continue
        try:
            git("merge", "--no-ff", "--no-edit", "-m", f"merge: {up_branch} into {branch}", up_branch, cwd=integ)
        except DispatchError:
            git("merge", "--abort", cwd=integ, check=False)
            raise DispatchError(f"story {sid}: merging upstream {up_branch} conflicts; fix the plan")
    return integ


def cmd_prepare(st: State, args) -> dict:
    # A lesson just recorded by `learn` is the one change that may wait to be committed.
    if not args.allow_dirty and clean_tree(st.root, ignore=(plan.CONSTRAINTS_FILE, ".agents/")):
        raise DispatchError("the main checkout has uncommitted changes (use --allow-dirty to proceed)")
    epic, stories = st.plans()
    errs = plan.validate_set(epic, stories)
    if errs:
        return {"ok": False, "errors": errs}
    by_id = {plan.story_key(s): s for s in stories}
    lessons = plan.load_constraints(str(st.root / plan.CONSTRAINTS_FILE))
    runnable = plan.next_runnable(epic, stories, args.max)
    briefs = st.work / "briefs"
    briefs.mkdir(parents=True, exist_ok=True)
    out = []
    for u in runnable:
        sid, track = u["story"], str(u["track"])
        story = by_id[sid]
        branch = story_branch(story)
        tbranch = f"{branch}--{track}"
        tree = st.trees / f"{sid}-{track}"
        dry: list | None = [] if args.plan else None
        ensure_story_branch(st, story, by_id, dry)
        unit = f"{sid}/{track}"
        t = track_of(story, track)
        if dry is not None:
            dry.append(f"git worktree add -b {tbranch} {tree} {branch}")
            base_state = "not run"
        else:
            if not tree.exists():
                git("worktree", "add", "-b", tbranch, str(tree), branch)
            if not plan.is_command(t.get("verify")):
                base_state = "not run"  # check reports the missing verify
            elif unit not in st.data.get("baselines", {}) and clean_tree(tree):
                base_state = "not run"  # a reused worktree holding work: never clean it
            else:
                passed = baseline(st, unit, str(t.get("verify")), tree, args.baseline_timeout)
                base_state = "pass" if passed else "fail"
            forget(st, unit)  # a re-planned unit starts over
            record(st, unit, "prepare", restart=bool(st.data.get("history", {}).get(unit)))
            st.save()
            st.set_status(sid, track, "running")
        weak = base_state == "pass" and t.get("verify_baseline") != "pass"
        text = plan.brief(story, track, lessons) + (
            f"\n\n## Where to work\nWork only in `{tree}` (cd there first). "
            f"Your branch is `{tbranch}`; commit there.\n")
        if weak:
            text += WEAK_BRIEF.format(verify=t.get("verify"))
        lane = plan.lane_of(t, story, epic)
        if lane == "irreversible":
            text += HUMAN_BRIEF
        bpath = briefs / f"{sid}-{track}.md"
        bpath.write_text(text, encoding="utf-8")
        item = {"unit": unit, "kind": u["kind"], "worktree": str(tree), "branch": tbranch,
                "story_branch": branch, "owns": u["owns"], "verify": u["verify"], "brief": str(bpath),
                "baseline": base_state, "weak_check": weak, "lane": lane}
        if dry is not None:
            item["would_run"] = dry
        out.append(item)
    return {"ok": True, "dry_run": bool(args.plan), "units": out,
            "waiting": [] if out else report_waiting(epic, stories)}


def report_waiting(epic, stories) -> list[str]:
    nodes, deps = plan.units(epic, stories)
    status = {u: n["track"].get("status", "todo") for u, n in nodes.items()}
    return [f"{u} waits on {', '.join(d for d in deps[u] if status.get(d) != 'done')}"
            for u in sorted(nodes) if status[u] == "todo"]


def cmd_check(st: State, args) -> dict:
    sid, track = split_unit(args.unit)
    story = st.story(sid)
    t = track_of(story, track)
    branch = story_branch(story)
    tree = st.trees / f"{sid}-{track}"
    if not tree.is_dir():
        raise DispatchError(f"no worktree for {args.unit} at {tree}")
    findings: list[str] = []
    dirty = clean_tree(tree)
    if dirty:
        findings.append(f"uncommitted changes: {', '.join(dirty[:10])}")
    commits = git("log", "--oneline", f"{branch}..HEAD", cwd=tree).splitlines()
    if not commits:
        findings.append("no commits on the track branch")
    changed = [c for c in git("diff", "--name-only", f"{branch}...HEAD", cwd=tree).splitlines() if c]
    outside = [c for c in changed if not plan.covered_by(c, plan.as_list(t.get("owns")))]
    if outside:
        findings.append(f"changed outside owns: {', '.join(outside)}")
    retry = st.data.get("retries", {}).get(args.unit)
    if retry:  # a returned unit fixes its findings and nothing else
        since = [c for c in git("diff", "--name-only", f"{retry['head']}...HEAD", cwd=tree).splitlines() if c]
        named = " ".join(retry["findings"] + [retry["note"]])
        widened = [c for c in since if c not in retry["changed"] and c not in named]
        if widened:
            findings.append(f"retry widened its scope beyond the findings: {', '.join(widened)}")
    epic = st.plans()[0]
    lane = plan.lane_of(t, story, epic)
    hard = plan.irreversible_paths(changed, story, epic)
    if hard:
        lane = "irreversible"  # the diff decides, whatever the plan predicted
    st.data.setdefault("lanes", {})[args.unit] = lane
    weak = weak_check(st, args.unit, t)
    if weak and not any(TEST_FILE.search(c) for c in changed):
        findings.append(f"verify passed before any work and the diff adds or changes no test, "
                        f"so the check cannot fail: {t.get('verify')}")
    verify_ok, tail = None, ""
    if not plan.is_command(t.get("verify")):
        tail = "not run: no verify command"
        findings.append("the plan has no verify command for this track")
    elif dirty:
        tail = "not run: the worktree has uncommitted changes"
    else:
        verify_ok, tail = run_shell(str(t.get("verify")), tree, args.timeout)
        restore(tree)
        if not verify_ok:
            findings.append(f"verify failed: {t.get('verify')}")
    owns = " ".join(f"'{p}'" for p in plan.as_list(t.get("owns")))
    st.data.setdefault("checks", {})[args.unit] = {
        "ok": not findings, "head": git("rev-parse", "HEAD", cwd=tree), "changed": changed,
        "findings": findings, "verify_tail": tail}
    record(st, args.unit, "check", ok=not findings, findings=findings, lane=lane)
    st.save()
    return {"ok": not findings, "unit": args.unit, "findings": findings, "commits": commits,
            "changed": changed, "outside_owns": outside, "verify": t.get("verify"),
            "verify_passed": verify_ok, "verify_tail": tail, "weak_check": weak,
            "lane": lane, "irreversible_paths": hard,
            "history": st.data["history"][args.unit],
            "review": f"git -C '{tree}' diff {branch}...HEAD -- {owns}"}


MAX_ATTEMPTS = 3

RETURN_BRIEF = """

## Attempt {attempt} of {max}: returned after {cause}
{intro}

{findings}

Lead's note: {note}

Last verify output:

```
{tail}
```

Fix only these findings, inside the paths you own. Keep the work that
already passes; do not rewrite it, and do not fix anything the findings
don't name. If they can't be fixed inside your paths, stop and say so.
"""


def forget(st: State, unit: str) -> None:
    """Drop a unit's retry history once it reaches a fresh start or is merged."""
    for key in ("attempts", "retries", "checks", "lanes", "needs_input"):
        st.data.get(key, {}).pop(unit, None)
    if unit in st.data.get("replan", []):
        st.data["replan"].remove(unit)


RETURN_CAUSES = {
    "check": ("a failed check", "Your previous attempt failed these checks:"),
    "review": ("a diff review", "Your previous attempt passed its check, but the diff review found these problems:"),
}


LIST_MARKER = re.compile(r"^(?:[-*]\s+\[[ xX]\]|[-*]|\d+[.)])(?:\s+|$)")


def read_review(path: str) -> list[str]:
    """A diff review's findings: one per non-empty line, with one list marker
    dropped: a `-` or `*` bullet, an ordered `1.` or `1)`, or a `- [ ]` checkbox."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DispatchError(f"cannot read the review findings {path}: {exc}") from exc
    findings = [LIST_MARKER.sub("", line.strip()) for line in text.splitlines()]
    findings = [f for f in findings if f]
    if not findings:
        raise DispatchError(f"the review findings {path} are empty")
    return findings


def cmd_retry(st: State, args) -> dict:
    sid, track = split_unit(args.unit)
    t = track_of(st.story(sid), track)
    if t.get("status", "todo") != "running":
        raise DispatchError(f"{args.unit} is {t.get('status', 'todo')}, not running; only a running unit can be retried")
    if not (st.trees / f"{sid}-{track}").is_dir():
        raise DispatchError(f"{args.unit} has no worktree to return to")
    last = st.data.get("checks", {}).get(args.unit)
    if not last or last.get("returned"):
        raise DispatchError(f"{args.unit} has no new check to return; run dispatch.py check first")
    review = read_review(args.review_findings) if args.review_findings else []
    if last["ok"] and not review:
        raise DispatchError(f"{args.unit} passed its last check; merge it instead "
                            "(or return a diff review's findings with --review-findings FILE)")
    source = "review" if last["ok"] else "check"  # a failed check stays a check retry
    findings = last["findings"] + review
    attempts = st.data.setdefault("attempts", {})
    attempt = attempts.get(args.unit, 1) + 1
    if attempt > MAX_ATTEMPTS + 1:  # past the one informed attempt `escalate` grants
        raise DispatchError(f"{args.unit} has used its informed attempt {MAX_ATTEMPTS + 1}; there is no "
                            f"attempt {attempt}: escalate it with --outcome replan or needs-input")
    if attempt > MAX_ATTEMPTS:
        outcome = (f"{MAX_ATTEMPTS} attempts were rejected by diff review" if source == "review"
                   else f"failed {MAX_ATTEMPTS} attempts")
        note = (f"replan: {outcome}, so the plan that produced it needs fixing "
                f"(story-decomposer); last findings: {'; '.join(findings)}")
        st.set_status(sid, track, "blocked", note)
        last["returned"] = True
        if review:  # a diff review rejected this passing work, so escalate may discard it
            last["review"] = review
        record(st, args.unit, "replan", note=note, source=source)
        replan = st.data.setdefault("replan", [])
        if args.unit not in replan:
            replan.append(args.unit)
        st.save()
        return {"ok": False, "unit": args.unit, "replan": True, "note": note}
    attempts[args.unit] = attempt
    record(st, args.unit, "retry", note=args.note, source=source, findings=findings)
    last["returned"] = True  # the next retry needs a new check of the new attempt
    st.data.setdefault("retries", {})[args.unit] = {
        "head": last["head"], "changed": last["changed"], "findings": findings, "note": args.note}
    original = (st.work / "briefs" / f"{sid}-{track}.md").read_text(encoding="utf-8")
    brief = st.work / "briefs" / f"{sid}-{track}-attempt{attempt}.md"
    brief.write_text(original + RETURN_BRIEF.format(
        attempt=attempt, max=MAX_ATTEMPTS, note=args.note, tail=last["verify_tail"] or "(not run)",
        cause=RETURN_CAUSES[source][0], intro=RETURN_CAUSES[source][1],
        findings="\n".join(f"- {f}" for f in findings)), encoding="utf-8")
    st.set_status(sid, track, "running", f"attempt {attempt}/{MAX_ATTEMPTS}: {args.note}")
    st.save()
    return {"ok": True, "unit": args.unit, "attempt": attempt, "max_attempts": MAX_ATTEMPTS,
            "brief": str(brief), "worktree": str(st.trees / f"{sid}-{track}")}


def check_lesson(paths: list[str], text: str, flags: str = "--constraint and every --paths value") -> None:
    if not text.strip() or not paths or any(not p.strip() for p in paths):
        raise DispatchError(f"{flags} must be non-empty")


def add_lesson(st: State, unit: str, paths: list[str], text: str) -> dict:
    """Append a lesson to the constraints file unless an identical one is there."""
    path = st.root / plan.CONSTRAINTS_FILE
    existing = plan.load_constraints(str(path))
    entry = {"paths": list(paths), "constraint": text.strip(), "source": unit,
             "date": datetime.date.today().isoformat()}
    if any(c["paths"] == entry["paths"] and c["constraint"].strip() == entry["constraint"] for c in existing):
        return {"ok": True, "recorded": False, "file": str(path), "note": "already recorded"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.dump({"constraints": [*existing, entry]}), encoding="utf-8")
    return {"ok": True, "recorded": True, "file": str(path), "constraint": entry,
            "next": f"commit {plan.CONSTRAINTS_FILE} so later runs and other machines see it"}


def cmd_learn(st: State, args) -> dict:
    """Record a confirmed cause as a planning constraint for later runs."""
    sid, track = split_unit(args.unit)
    track_of(st.story(sid), track)
    check_lesson(args.paths, args.constraint)
    return add_lesson(st, args.unit, args.paths, args.constraint)


def rejections(st: State, unit: str) -> str:
    """How a unit's attempts ran out, from its history: failed checks, diff
    review rejections of passing work, or both."""
    sources = {e.get("source", "check") for e in st.data.get("history", {}).get(unit, [])
               if e["event"] in ("retry", "replan")}
    last = st.data.get("checks", {}).get(unit)
    if last and not last["ok"]:
        sources.add("check")
    phrases = {"check": "failed their check", "review": "were rejected by diff review"}
    return " or ".join(phrases[s] for s in ("check", "review") if s in sources) or phrases["check"]


ESCALATED_BRIEF = """

## Attempt {attempt}: one informed attempt after {max} failed
The first {max} attempts {failed}. The lead diagnosed why; read the
diagnosis before you change anything, and act on its cause rather than on the
symptoms. Your worktree was reset to the story branch, so start from there.
This is the last attempt: if the diagnosis is wrong or the fix needs paths
you do not own, stop and say so.

### Diagnosis
{diagnosis}
"""

OUTCOMES = ("attempt", "replan", "needs-input")


def story_issue(st: State, sid: str, story: dict) -> str | None:
    """The story's issue reference: its plan's `issue`, the issue it was loaded
    from, or the epic's entry for it."""
    refs = [story.get("issue")]
    src = st.data.get("sources", {}).get(f"story-{sid}.md", {})
    if src.get("kind") == "tracker":
        refs.append(src.get("ref"))
    epic = st.plans()[0]
    refs += [s.get("issue") for s in plan.as_list((epic or {}).get("stories")) if str(s.get("id")) == sid]
    return next((str(r) for r in refs if plan.issue_number(r)), None)


def cmd_escalate(st: State, args) -> dict:
    """Climb the ladder after a unit's attempts run out: grant one informed
    attempt, route it to one replan, or hand it to a person, then post the
    diagnosis once the state has recorded it."""
    unit = args.unit
    sid, track = split_unit(unit)
    story = st.story(sid)
    track_of(story, track)
    # Validate everything before anything is posted or changed.
    if unit in st.data.get("needs_input", {}):
        raise DispatchError(f"{unit} is waiting on a person: they must answer "
                            f"{st.data['needs_input'][unit]!r} before it can be escalated again")
    attempts = st.data.get("attempts", {}).get(unit, 1)
    if attempts < MAX_ATTEMPTS and unit not in st.data.get("replan", []):
        raise DispatchError(f"{unit} is on attempt {attempts} of {MAX_ATTEMPTS}; escalate only a unit that has "
                            "used its attempts or is blocked for replanning (use retry)")
    try:
        diagnosis = Path(args.diagnosis).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise DispatchError(f"cannot read the diagnosis {args.diagnosis}: {exc}") from exc
    if not diagnosis:
        raise DispatchError(f"the diagnosis {args.diagnosis} is empty")
    past = [e.get("outcome") for e in st.data.get("history", {}).get(unit, []) if e["event"] == "escalate"]
    if "replan" in past and args.outcome != "needs-input":
        raise DispatchError(f"{unit} was already replanned once; only --outcome needs-input is left")
    if args.outcome == "attempt" and "attempt" in past:
        raise DispatchError(f"{unit} already had its informed attempt; an attempt is granted once")
    question = (args.question or "").strip()
    if args.outcome == "needs-input" and not question:
        raise DispatchError("--outcome needs-input needs --question: what the person must answer")
    lesson_paths = list(args.lesson_paths or [])
    if args.lesson is not None or lesson_paths:
        if args.lesson is None or not lesson_paths:
            raise DispatchError("--lesson and --lesson-paths go together")
        plan.load_constraints(str(st.root / plan.CONSTRAINTS_FILE))
        check_lesson(lesson_paths, args.lesson, "--lesson and every --lesson-paths value")
    tree = st.trees / f"{sid}-{track}"
    branch = story_branch(story)
    tbranch = f"{branch}--{track}"
    last = st.data.get("checks", {}).get(unit)
    if args.outcome == "attempt" and last and last["ok"] and not last.get("review"):
        raise DispatchError(f"{unit} passed its last check; merge it instead")
    if args.outcome == "attempt" and tree.is_dir() and clean_tree(tree):
        raise DispatchError(f"{tree} has uncommitted changes; commit or remove them before it is reset")

    # Do the local work first and post last, so the issue never shows an
    # escalation that the state did not record.
    rung = len(past) + 1
    issue = story_issue(st, sid, story)
    result = {"ok": True, "unit": unit, "rung": rung, "outcome": args.outcome, "commented_on": issue}
    if last:
        last["returned"] = True
    replan = st.data.setdefault("replan", [])

    if args.outcome == "attempt":
        failed = rejections(st, unit)  # before the reset drops the last check
        attempt = MAX_ATTEMPTS + 1
        if tree.is_dir():
            git("checkout", "-f", "-B", tbranch, branch, cwd=tree)
            git("clean", "-fdq", cwd=tree)
        else:
            git("worktree", "add", "-B", tbranch, str(tree), branch)
        st.data.setdefault("attempts", {})[unit] = attempt
        for key in ("retries", "checks"):  # the reset discards what they describe
            st.data.get(key, {}).pop(unit, None)
        if unit in replan:
            replan.remove(unit)
        briefs = st.work / "briefs"
        original = (briefs / f"{sid}-{track}.md")
        text = original.read_text(encoding="utf-8") if original.is_file() else ""
        brief = briefs / f"{sid}-{track}-attempt{attempt}.md"
        briefs.mkdir(parents=True, exist_ok=True)
        brief.write_text(text + ESCALATED_BRIEF.format(attempt=attempt, max=MAX_ATTEMPTS, failed=failed,
                                                           diagnosis=diagnosis),
                         encoding="utf-8")
        st.set_status(sid, track, "running", f"attempt {attempt}: informed by a diagnosis")
        result.update(attempt=attempt, brief=str(brief), worktree=str(tree))
    elif args.outcome == "replan":
        st.set_status(sid, track, "blocked", diagnosis)
        if unit not in replan:
            replan.append(unit)
    else:
        st.set_status(sid, track, "blocked", question)
        if unit in replan:
            replan.remove(unit)
        st.data.setdefault("needs_input", {})[unit] = question
        result["question"] = question
    record(st, unit, "escalate", rung=rung, outcome=args.outcome)
    st.save()
    if args.lesson is not None:
        result["lesson"] = add_lesson(st, unit, lesson_paths, args.lesson)
    if issue:
        tracker = _load("tracker")
        tracker.forge().comment(tracker.number(issue), (
            f"**Escalation of {unit}** (rung {rung}, outcome `{args.outcome}`)\n\n{diagnosis}\n"
            + (f"\n**Question:** {question}\n" if question else "")))
    else:
        result["note"] = "the story has no issue; the diagnosis was not posted"
    return result


def cmd_block(st: State, args) -> dict:
    sid, track = split_unit(args.unit)
    track_of(st.story(sid), track)
    st.set_status(sid, track, "blocked", args.note)
    record(st, args.unit, "block", note=args.note)
    st.save()
    return {"ok": True, "unit": args.unit, "status": "blocked", "note": args.note}


def cmd_merge(st: State, args) -> dict:
    sid, track = split_unit(args.unit)
    story = st.story(sid)
    t = track_of(story, track)
    status = {str(x.get("id")): x.get("status", "todo") for x in plan.as_list(story.get("tracks"))}
    if status[track] != "running":
        raise DispatchError(f"{args.unit} is {status[track]}, not running")
    waiting = [d for d in map(str, plan.as_list(t.get("depends_on"))) if status.get(d) != "done"]
    order = [str(x) for x in plan.as_list((story.get("integration") or {}).get("merge_order"))]
    if track in order:
        waiting += [x for x in order[: order.index(track)] if status.get(x) != "done" and x not in waiting]
    if waiting:
        return {"ok": False, "unit": args.unit, "findings": [f"merge {', '.join(waiting)} first"]}
    # Decide from what is actually being merged, not from a stored check: a
    # merge without a prior check (or after a re-prepare) still sees the diff.
    branch = story_branch(story)
    epic = st.plans()[0]
    merging = [c for c in git("diff", "--name-only", f"{branch}...{branch}--{track}").splitlines() if c]
    lane = ("irreversible" if plan.irreversible_paths(merging, story, epic)
            else plan.lane_of(t, story, epic))
    if lane == "irreversible" and not args.human:
        return {"ok": False, "unit": args.unit, "lane": lane,
                "findings": [f"{args.unit} is in the irreversible lane: a person must approve this merge; "
                             "after they do, run `dispatch.py merge <unit> --human`"]}
    tree = st.trees / f"{sid}-{track}"
    dirty = clean_tree(tree) if tree.is_dir() else []
    if dirty:  # merging would delete this worktree, and these files with it
        return {"ok": False, "unit": args.unit,
                "findings": [f"uncommitted changes in the worktree: {', '.join(dirty[:10])}; "
                             "commit them and re-run check first"]}
    by_id = {plan.story_key(s): s for s in st.plans()[1]}
    integ = ensure_story_branch(st, story, by_id, None)
    branch = story_branch(story)
    tbranch = f"{branch}--{track}"
    try:
        git("merge", "--no-ff", "--no-edit", "-m", f"merge({sid}): track {track}", tbranch, cwd=integ)
    except DispatchError:
        conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=integ, check=False).splitlines()
        git("merge", "--abort", cwd=integ, check=False)
        if not conflicts:
            raise  # an environment failure (identity, hooks, locks): fix it, don't blame the plan
        note = f"merge conflict in {', '.join(conflicts)}; the plan's ownership is wrong"
        st.set_status(sid, track, "blocked", note)
        record(st, args.unit, "conflict", files=conflicts)
        st.save()
        return {"ok": False, "unit": args.unit, "findings": [note]}
    sha = git("rev-parse", "--short", "HEAD", cwd=integ)
    st.set_status(sid, track, "done", f"merged {sha}")
    record(st, args.unit, "merge", sha=sha, lane=lane, human=bool(args.human))
    forget(st, args.unit)
    st.save()
    if tree.exists():
        git("worktree", "remove", "--force", str(tree))
    git("branch", "-D", tbranch, check=False)
    st.data.get("lanes", {}).pop(args.unit, None)
    st.save()
    return {"ok": True, "unit": args.unit, "merged": sha, "story_branch": branch, "lane": lane}


def shipped(story: dict, ref: str) -> bool:
    """Whether an upstream story's work is already in `ref`: its branch is gone
    (merged and deleted), merged into `ref`, or its owned paths match `ref`
    (squashed, or shipped as stacked per-track PRs)."""
    branch = story_branch(story)
    if not ok("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"):
        return True
    if ok("merge-base", "--is-ancestor", branch, ref):
        return True
    specs = [f":(glob){p}" for p in plan.as_list(story.get("owns"))]
    return bool(specs) and ok("diff", "--quiet", ref, branch, "--", *specs)


def cmd_integrate(st: State, args) -> dict:
    story = st.story(args.story)
    pending = [str(x.get("id")) for x in plan.as_list(story.get("tracks")) if x.get("status") != "done"]
    if pending:
        return {"ok": False, "story": args.story, "findings": [f"tracks not done: {', '.join(pending)}"]}
    by_id = {plan.story_key(s): s for s in st.plans()[1]}
    integ = ensure_story_branch(st, story, by_id, None)
    dirty = clean_tree(integ)
    if dirty:  # verify on an unknown tree means nothing, and cleanup would erase it
        return {"ok": False, "story": args.story,
                "findings": [f"uncommitted changes in {integ}: {', '.join(dirty[:10])}; "
                             "commit or remove them first"]}
    upstreams = [str(u) for u in plan.as_list(story.get("depends_on"))]
    base = {"story": args.story, "branch": story_branch(story), "upstreams": upstreams}
    if args.sync:  # before a PR: the upstreams must have shipped, then the PR shows only this story
        waiting = [u for u in upstreams if u in by_id and not shipped(by_id[u], args.sync)]
        if waiting:
            return {"ok": False, **base, "findings": [
                f"upstream stories not merged into {args.sync} yet: {', '.join(waiting)}; ship them first"]}
        try:
            git("merge", "--no-ff", "--no-edit", "-m", f"merge: {args.sync} into {base['branch']}", args.sync,
                cwd=integ)
        except DispatchError:
            conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=integ, check=False).splitlines()
            git("merge", "--abort", cwd=integ, check=False)
            if not conflicts:
                raise  # a bad ref or an environment failure (identity, hooks, locks): not a conflict
            return {"ok": False, **base, "findings": [
                f"merging {args.sync} conflicts in {', '.join(conflicts)}; resolve it on the story branch"]}
    results, findings = [], []
    commands = [c for c in [(story.get("integration") or {}).get("verify"), story.get("verify")]
                if plan.is_command(c)]
    if not commands:
        findings.append("the plan has no verify command for this story (integration.verify or verify)")
    for command in dict.fromkeys(commands):
        passed, tail = run_shell(str(command), integ, args.timeout)
        restore(integ)
        results.append({"command": command, "passed": passed, "tail": tail})
        if not passed:
            findings.append(f"failed: {command}")
    pushed = False
    if not findings and args.push and git("remote", check=False):
        git("push", "-u", "origin", story_branch(story), cwd=integ)
        pushed = True
    order = plan.as_list((story.get("integration") or {}).get("merge_order")) or [
        t.get("id") for t in plan.as_list(story.get("tracks"))]
    merged = {str(t): next((e.get("sha") for e in reversed(st.data.get("history", {}).get(f"{args.story}/{t}", []))
                            if e["event"] == "merge"), None) for t in order}
    return {"ok": not findings, **base, "ship": story.get("ship", "story"), "merged": merged,
            "checks": results, "findings": findings, "pushed": pushed}


def cmd_report(st: State, args) -> dict:  # noqa: ARG001
    epic, stories = st.plans()
    rows, done_stories = [], []
    for s in stories:
        tracks = plan.as_list(s.get("tracks"))
        for t in tracks:
            rows.append({"unit": f"{plan.story_key(s)}/{t.get('id')}", "status": t.get("status", "todo"),
                         "note": t.get("note", "")})
        if tracks and all(t.get("status") == "done" for t in tracks):
            done_stories.append(plan.story_key(s))
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in plan.STATUSES}
    for r in rows:
        r["attempts"] = st.data.get("attempts", {}).get(r["unit"], 1)
        r["history"] = summarize(st.data.get("history", {}).get(r["unit"], []))
    return {"ok": True, "counts": counts, "units": rows, "stories_ready_to_integrate": done_stories,
            "needs_replan": st.data.get("replan", []),
            "needs_input": [{"unit": u, "question": q} for u, q in st.data.get("needs_input", {}).items()],
            "awaiting_human": sorted(
                u for u, lane in st.data.get("lanes", {}).items()
                if lane == "irreversible" and st.data.get("checks", {}).get(u, {}).get("ok")
                and next((r["status"] for r in rows if r["unit"] == u), None) == "running"),
            "next_runnable": [u["unit"] for u in plan.next_runnable(epic, stories, 99)],
            "waiting": report_waiting(epic, stories)}


def positive_seconds(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical steps of wave-dispatcher (git, plans, status).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("load")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--epic"); g.add_argument("--story", nargs="+"); g.add_argument("--files", nargs="+")
    p.add_argument("--base", help="branch new story branches start from (default: origin/HEAD, main or master)")
    p = sub.add_parser("prepare"); p.add_argument("--max", type=int, default=3)
    p.add_argument("--plan", action="store_true", help="dry run: write briefs, print the git commands, change nothing")
    p.add_argument("--allow-dirty", action="store_true")
    p.add_argument("--baseline-timeout", type=positive_seconds, default=300,
                   help="seconds for the one-time verify run that detects a check that cannot fail")
    p = sub.add_parser("retry", help="return a failed unit with its evidence (max 3 attempts)")
    p.add_argument("unit"); p.add_argument("--note", required=True)
    p.add_argument("--review-findings", metavar="FILE",
                   help="a diff review's findings, one per line: returns the unit even if its check passed")
    p = sub.add_parser("check"); p.add_argument("unit"); p.add_argument("--timeout", type=int, default=900)
    p = sub.add_parser("merge"); p.add_argument("unit")
    p.add_argument("--human", action="store_true", help="a person approved this irreversible-lane merge")
    p = sub.add_parser("block"); p.add_argument("unit"); p.add_argument("--note", required=True)
    p = sub.add_parser("learn", help="record a confirmed cause as a constraint for later plans")
    p.add_argument("--unit", required=True); p.add_argument("--paths", nargs="+", required=True)
    p.add_argument("--constraint", required=True)
    p = sub.add_parser("escalate", help="after the attempts run out: post a diagnosis and take one rung")
    p.add_argument("unit"); p.add_argument("--diagnosis", required=True, help="file with the diagnosis")
    p.add_argument("--outcome", required=True, choices=OUTCOMES)
    p.add_argument("--question", help="what a person must answer (required for needs-input)")
    p.add_argument("--lesson-paths", nargs="+", help="globs the lesson applies to")
    p.add_argument("--lesson", help="a confirmed cause, recorded as a planning constraint")
    p = sub.add_parser("integrate"); p.add_argument("story"); p.add_argument("--push", action="store_true")
    p.add_argument("--sync", metavar="REF", help="merge REF (e.g. origin/main) in first; refuses until upstreams are in it")
    p.add_argument("--timeout", type=int, default=1800)
    sub.add_parser("report")
    args = ap.parse_args()
    try:
        st = State()
        result = globals()[f"cmd_{args.cmd}"](st, args)
    except (DispatchError, plan.PlanError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    except SystemExit as exc:  # tracker.py reports its failures with sys.exit("tracker: ...")
        if exc.code in (None, 0):
            raise
        print(json.dumps({"ok": False, "error": str(exc.code)}, indent=2))
        return 2
    except (OSError, ValueError) as exc:  # includes a corrupt state.json (JSONDecodeError)
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    raise SystemExit(main())
