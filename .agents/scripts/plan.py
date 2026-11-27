#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Read, check and schedule the `agent-plan` blocks in Epic and story bodies.

An Epic or story body (a GitHub/Gitea issue saved to a file) ends with one
fenced block whose info string is `yaml agent-plan`. That block is the source
of truth for stories, tracks, tasks, ownership, dependencies and verify
commands; the schema is `.agents/doctrine/agent-plan-schema.md`.

Commands (FILE is a markdown body, a bare YAML file, or - for stdin):

  extract  FILE                 print the plan block as YAML (--json for JSON)
  validate FILE...              check schema, references, cycles, ownership
  waves    FILE...              print the computed waves
  render   FILE                 print the markdown sections generated from the plan
  sync     FILE                 rewrite those sections in FILE from its plan
  next     FILE... [--max N]    JSON list of tracks that can start now
  brief    FILE --track ID      the subagent brief for one track
  scope    FILE --track ID --changed PATH...   fail if a path is outside `owns`
  status   FILE --track ID --set todo|running|done|blocked [--note TEXT]
  check    FILE... [--no-sync]   validate + sync + prose shape + waves, one report
  scaffold EPIC [--out DIR] [--stories S1,S2] [--force]
                                write story-<id>.md skeletons with the plan prefilled

Exit codes: 0 ok, 1 validation/scope failure, 2 usage or unreadable input.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # re-run under uv with PyYAML rather than vendoring a parser
    if shutil.which("uv") and not os.environ.get("AGENT_PLAN_REEXEC"):
        os.environ["AGENT_PLAN_REEXEC"] = "1"
        os.execvp("uv", ["uv", "run", "--quiet", "--script", __file__, *sys.argv[1:]])
    sys.exit("plan.py needs PyYAML: install it, or install uv so it can fetch it")

FENCE = re.compile(r"^```ya?ml[ \t]+agent-plan[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
GEN_START = "<!-- agent-plan:generated -->"
GEN_END = "<!-- /agent-plan:generated -->"
STATUSES = ("todo", "running", "done", "blocked")
SIZES = ("S", "M", "L")
STORY_TYPES = ("user", "spike", "technical", "bug")
TRACK_KINDS = ("contract", "track")
LANES = ("contained", "wide", "irreversible")
SHIP_MODES = ("story", "per-track")  # one PR for the story, or one stacked PR per track
# Paths where a bad merge can't simply be reverted: schema and data
# migrations, and anything that deploys or changes infrastructure. A plan can
# add its own with `lanes: {irreversible: [...]}`.
IRREVERSIBLE_GLOBS = (
    "**/migrations/**", "**/alembic/**", "**/*.sql", "supabase/**",
    "deploy/**", "deployments/**", "infra/**", "k8s/**", "helm/**", "terraform/**", "**/*.tf",
)


class PlanError(Exception):
    pass


class _PlainDumper(yaml.SafeDumper):
    """No `&id001` anchors: a plan is read by people and agents, not just yaml."""

    def ignore_aliases(self, data):  # noqa: ARG002
        return True


def dump(data: dict) -> str:
    return yaml.dump(data, Dumper=_PlainDumper, sort_keys=False, allow_unicode=True, width=100)


# ── loading ──────────────────────────────────────────────────────────────────

def read_text(path: str) -> str:
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanError(f"{path}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise PlanError(f"{path}: not UTF-8 text ({exc.reason})") from exc


def extract(text: str, source: str = "input") -> dict:
    text = text.replace("\r\n", "\n")
    blocks = FENCE.findall(text)
    if len(blocks) > 1:
        raise PlanError(f"{source}: {len(blocks)} agent-plan blocks; keep exactly one")
    if blocks:
        try:
            data = yaml.safe_load(blocks[0])
        except yaml.YAMLError as exc:
            raise PlanError(f"{source}: plan is not valid YAML: {exc}") from exc
    else:
        # A bare YAML file is a plan only if it parses to a mapping with a kind;
        # markdown (even one starting with `# heading`) is not.
        try:
            data = yaml.safe_load(text) if text.strip() else None
        except yaml.YAMLError:
            data = None
        if not (isinstance(data, dict) and "kind" in data):
            raise PlanError(f"{source}: no ```yaml agent-plan block found")
    if not isinstance(data, dict):
        raise PlanError(f"{source}: plan must be a mapping")
    for field in ("stories", "contracts", "tracks", "tasks"):
        for i, entry in enumerate(as_list(data.get(field))):
            if not isinstance(entry, dict):
                raise PlanError(f"{source}: {field}[{i}] is {entry!r}; each entry needs fields "
                                f"(e.g. `- id: {entry}`)")
    return data


def load(paths: list[str], texts: dict[str, str] | None = None) -> tuple[dict | None, list[dict]]:
    """Returns (epic plan or None, story plans).

    `texts` holds any input already read (stdin can only be read once).
    """
    epic, stories = None, []
    texts = texts or {}
    for path in paths:
        text = texts[path] if path in texts else read_text(path)
        plan = extract(text, path)
        plan["_source"] = path
        kind = plan.get("kind")
        if kind == "epic":
            if epic is not None:
                raise PlanError("more than one epic plan given")
            epic = plan
        elif kind == "story":
            stories.append(plan)
        else:
            raise PlanError(f"{path}: kind must be epic or story, got {kind!r}")
    return epic, stories


# ── helpers ──────────────────────────────────────────────────────────────────

def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def segments(pattern: str) -> list[str]:
    """`./src/api/` -> [src, api]. Empty and `.` segments are dropped."""
    return [p for p in str(pattern).strip().replace("\\", "/").split("/") if p not in ("", ".")]


def wild(segment: str) -> bool:
    return any(ch in segment for ch in "*?[")


def is_open(pattern: str) -> bool:
    """A pattern ending in a literal names a file *or* a directory, so it also
    covers everything below it: owning `app/reports` owns `app/reports/x.py`."""
    segs = segments(pattern)
    return not segs or not wild(segs[-1]) or segs[-1] == "**"


def seg_meets(a: str, b: str) -> bool:
    """Can one path segment satisfy both segment patterns?"""
    if not wild(a) and not wild(b):
        return a == b
    if not wild(a):
        return fnmatch.fnmatchcase(a, b)
    if not wild(b):
        return fnmatch.fnmatchcase(b, a)
    return True  # two wildcards: assume they can meet (conservative)


def _meet(a: list[str], b: list[str], open_a: bool, open_b: bool) -> bool:
    if a and a[0] == "**":
        return _meet(a[1:], b, open_a, open_b) or (bool(b) and _meet(a, b[1:], open_a, open_b))
    if b and b[0] == "**":
        return _meet(a, b[1:], open_a, open_b) or (bool(a) and _meet(a[1:], b, open_a, open_b))
    if not a and not b:
        return True
    if not a:
        return open_a
    if not b:
        return open_b
    return seg_meets(a[0], b[0]) and _meet(a[1:], b[1:], open_a, open_b)


def patterns_meet(pa: str, pb: str) -> bool:
    """True when some path could be matched by both ownership patterns."""
    return _meet(segments(pa), segments(pb), is_open(pa), is_open(pb))


def overlaps(a: list, b: list) -> list[tuple[str, str]]:
    """Pairs of patterns that may touch the same file."""
    return [(pa, pb) for pa in a for pb in b if patterns_meet(str(pa), str(pb))]


def _covers(pat: list[str], path: list[str], open_pat: bool) -> bool:
    if not pat:
        return not path or open_pat
    if pat[0] == "**":
        return _covers(pat[1:], path, open_pat) or (bool(path) and _covers(pat, path[1:], open_pat))
    if not path:
        return False
    return fnmatch.fnmatchcase(path[0], pat[0]) and _covers(pat[1:], path[1:], open_pat)


def covered_by(path: str, owns: list) -> bool:
    """Is a concrete path (e.g. from `git diff --name-only`) inside `owns`?"""
    parts = segments(path)
    return any(_covers(segments(p), parts, is_open(str(p))) for p in owns)


def subsumed(pattern: str, owns: list) -> bool:
    """Is everything `pattern` can match also inside `owns`?"""
    if any(str(pattern).strip().rstrip("/") == str(o).strip().rstrip("/") for o in owns):
        return True
    segs = segments(pattern)
    head = []
    for seg in segs:
        if wild(seg):
            break
        head.append(seg)
    if len(head) == len(segs):  # a literal file or directory
        probe = "/".join(head + ["\x00probe"]) if is_open(pattern) else "/".join(head)
        return covered_by("/".join(head), owns) and covered_by(probe, owns)
    # A wildcard below `head`: everything under head must be owned.
    return covered_by("/".join(head + ["\x00probe"]), owns)


PLACEHOLDER = re.compile(r"^\s*(?:<[^>]*>|\[[^\]]*\]|tbd|todo|n/?a|none)?\s*$", re.IGNORECASE)


def is_command(value) -> bool:
    return isinstance(value, str) and not PLACEHOLDER.match(value)


def validate_consumes(where: str, entry: dict, owns_of: dict[str, list]) -> list[str]:
    """`consumes: {<upstream>: [path or path::Symbol, ...]}`: each key is a
    dependency, and each path lies inside what that upstream owns."""
    consumes = entry.get("consumes")
    if consumes is None:
        return []
    if not isinstance(consumes, dict) or not all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in consumes.values()):
        return [f"{where}: consumes must map each dependency to a list of paths"]
    errs = []
    deps = {str(d) for d in as_list(entry.get("depends_on"))}
    for up, items in consumes.items():
        up = str(up)
        if up not in deps:
            errs.append(f"{where}: consumes from {up}, which it does not depend on")
            continue
        owns = as_list(owns_of.get(up))
        for item in items:
            path = item.split("::", 1)[0]
            if owns and not (covered_by(path, owns) or subsumed(path, owns)):
                errs.append(f"{where}: consumes {path} from {up}, which {up} does not own")
    return errs


def edge_warnings(epic: dict | None, stories: list[dict]) -> list[str]:
    """Dependencies that name nothing crossing them: "and then" edges that may
    serialize work for nothing. Warnings, not errors, until plans carry them."""
    def unnamed(entry: dict) -> list[str]:  # a dependency mapped to nothing names nothing
        consumes = entry.get("consumes") if isinstance(entry.get("consumes"), dict) else {}
        return [d for d in map(str, as_list(entry.get("depends_on"))) if not as_list(consumes.get(d))]

    out = []
    # The epic is authoritative for story edges; without one, use the story plans'.
    for s in as_list(epic.get("stories")) if epic else stories:
        sid = s.get("id") if epic else story_key(s)
        out += [f"story {sid} depends on {d} but names nothing it consumes from it" for d in unnamed(s)]
    for story in stories:
        for tr in as_list(story.get("tracks")):
            out += [f"story {story_key(story)} track {tr.get('id')} depends on {d} "
                    "but names nothing it consumes from it" for d in unnamed(tr)]
    return out


def validate_lanes(where: str, body: dict) -> list[str]:
    lanes = body.get("lanes")
    if lanes is None:
        return []
    if (not isinstance(lanes, dict) or set(lanes) - {"irreversible"}
            or not all(isinstance(g, str) for g in as_list(lanes.get("irreversible")))):
        return [f"{where}: lanes takes only `irreversible: [globs]`"]
    return []


def lane_of(track: dict, plan: dict, epic: dict | None = None) -> str:
    """How a track's merge is gated, by how hard a bad merge is to undo:
    irreversible (never auto-merged), wide (shared surface: checks plus review)
    or contained (checks only). An explicit `lane:` wins."""
    if track.get("lane") in LANES:
        return str(track["lane"])
    owns = [str(p) for p in as_list(track.get("owns"))]
    globs = irreversible_globs(plan, epic)
    def inside(pattern: str, targets: list[str]) -> bool:
        literal = not any(wild(s) for s in segments(pattern))
        return covered_by(pattern, targets) if literal else subsumed(pattern, targets)

    if any(inside(o, globs) for o in owns):
        return "irreversible"
    shared = [str(p) for c in as_list((epic or {}).get("contracts")) for p in as_list(c.get("paths"))]
    if track.get("kind") == "contract" or any(covered_by(s, [o]) or subsumed(o, [s]) for o in owns for s in shared):
        return "wide"
    return "contained"


def irreversible_globs(plan: dict, epic: dict | None = None) -> list[str]:
    extra = []
    for source in (epic or {}, plan):
        extra += [str(g) for g in as_list((source.get("lanes") or {}).get("irreversible"))]
    return [*IRREVERSIBLE_GLOBS, *extra]


def irreversible_paths(paths: list[str], plan: dict, epic: dict | None = None) -> list[str]:
    """The changed files that fall in an irreversible glob, whatever the lane
    the plan predicted: a track owning `backend/**` that adds a migration is
    irreversible for that diff."""
    globs = irreversible_globs(plan, epic)
    return [p for p in paths if covered_by(p, globs)]


def waiting_on_unplanned(nodes: list[str], deps: dict[str, list[str]]) -> list[str]:
    """Nodes that depend, directly or through others, on something with no plan
    yet (e.g. units()'s `<story>/<unplanned>` sentinel). The scheduler never
    starts them, so they belong in no wave."""
    known = set(nodes)
    waiting = {n for n in nodes if any(d not in known for d in deps.get(n, []))}
    grew = True
    while grew:
        more = {n for n in nodes if n not in waiting and waiting & set(deps.get(n, []))}
        waiting |= more
        grew = bool(more)
    return sorted(waiting)


def topo_levels(nodes: list[str], deps: dict[str, list[str]], what: str) -> list[list[str]]:
    """Kahn levels over the nodes that can run; raises on a cycle."""
    nodes = [n for n in nodes if n not in set(waiting_on_unplanned(nodes, deps))]
    remaining = {n: set(d for d in deps.get(n, []) if d in nodes) for n in nodes}
    levels = []
    while remaining:
        ready = sorted(n for n, d in remaining.items() if not d)
        if not ready:
            raise PlanError(f"dependency cycle among {what}: {', '.join(sorted(remaining))}")
        levels.append(ready)
        for n in ready:
            del remaining[n]
        for d in remaining.values():
            d.difference_update(ready)
    return levels


def ancestors(node: str, deps: dict[str, list[str]]) -> set[str]:
    seen, stack = set(), list(deps.get(node, []))
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(deps.get(n, []))
    return seen


def story_key(story: dict) -> str:
    return str(story.get("story") or story.get("id"))


# ── validation ───────────────────────────────────────────────────────────────

def validate_epic(epic: dict) -> list[str]:
    errs = validate_lanes("epic", epic)
    if epic.get("version") != 1:
        errs.append("epic: version must be 1")
    acs = [str(a) for a in as_list(epic.get("acs"))]
    if not 3 <= len(acs) <= 8:
        errs.append(f"epic: {len(acs)} acs; an epic has 3-8 (split it if more)")
    stories = as_list(epic.get("stories"))
    if not stories:
        errs.append("epic: no stories")
    ids = [str(s.get("id")) for s in stories]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errs.append(f"epic: duplicate story ids {sorted(dupes)}")
    deps = {str(s.get("id")): [str(d) for d in as_list(s.get("depends_on"))] for s in stories}
    covered = set()
    for s in stories:
        sid = str(s.get("id"))
        for field in ("title", "size", "owns"):
            if not s.get(field):
                errs.append(f"story {sid}: missing {field}")
        if not is_command(s.get("verify")):
            errs.append(f"story {sid}: missing verify (an exact command, not a placeholder)")
        if s.get("size") and s.get("size") not in SIZES:
            errs.append(f"story {sid}: size must be S, M or L")
        if s.get("type") and s.get("type") not in STORY_TYPES:
            errs.append(f"story {sid}: type must be one of {', '.join(STORY_TYPES)}")
        if s.get("status", "todo") not in STATUSES:
            errs.append(f"story {sid}: status must be one of {', '.join(STATUSES)}")
        story_acs = [str(a) for a in as_list(s.get("acs"))]
        unknown = [a for a in story_acs if a not in acs]
        if unknown:
            errs.append(f"story {sid}: unknown acs {unknown}")
        if not story_acs and not s.get("constraint"):
            errs.append(f"story {sid}: traces to no ac (set acs, or constraint: <reason>)")
        covered.update(story_acs)
        for d in deps[sid]:
            if d not in ids:
                errs.append(f"story {sid}: depends_on unknown story {d}")
        errs += validate_consumes(f"story {sid}", s, {str(x.get("id")): as_list(x.get("owns")) for x in stories})
    missing = [a for a in acs if a not in covered]
    if missing:
        errs.append(f"epic: acs with no story: {missing}")
    for c in as_list(epic.get("contracts")):
        if str(c.get("owner")) not in ids:
            errs.append(f"contract {c.get('id')}: owner {c.get('owner')} is not a story")
    try:
        topo_levels(ids, deps, "stories")
    except PlanError as exc:
        errs.append(str(exc))
        return errs
    errs += parallel_conflicts({i: as_list(s.get("owns")) for i, s in zip(ids, stories)}, deps, "stories")
    return errs


def validate_story(story: dict) -> list[str]:
    sid = story_key(story)
    errs = []
    if story.get("version") != 1:
        errs.append(f"story {sid}: version must be 1")
    for field in ("story", "owns", "tracks"):
        if not story.get(field):
            errs.append(f"story {sid}: missing {field}")
    if not story.get("acs") and not story.get("constraint"):
        errs.append(f"story {sid}: missing acs (set acs, or constraint: <reason>)")
    if not is_command(story.get("verify")):
        errs.append(f"story {sid}: missing verify (an exact command, not a placeholder)")
    errs += validate_lanes(f"story {sid}", story)
    errs += validate_consumes(f"story {sid}", story, {})
    tracks = as_list(story.get("tracks"))
    if story.get("ship", "story") not in SHIP_MODES:
        errs.append(f"story {sid}: ship must be one of {', '.join(SHIP_MODES)}")
    elif story.get("ship") == "per-track" and len(tracks) < 2:
        errs.append(f"story {sid}: ship: per-track needs more than one track")
    tids = [str(t.get("id")) for t in tracks]
    dupes = {i for i in tids if tids.count(i) > 1}
    if dupes:
        errs.append(f"story {sid}: duplicate track ids {sorted(dupes)}")
    deps = {str(t.get("id")): [str(d) for d in as_list(t.get("depends_on"))] for t in tracks}
    story_owns = as_list(story.get("owns"))
    for t in tracks:
        tid = str(t.get("id"))
        where = f"story {sid} track {tid}"
        if t.get("kind", "track") not in TRACK_KINDS:
            errs.append(f"{where}: kind must be contract or track")
        if "lane" in t and t["lane"] not in LANES:
            errs.append(f"{where}: lane must be one of {', '.join(LANES)}")
        errs += validate_consumes(where, t, {str(x.get("id")): as_list(x.get("owns")) for x in tracks})
        if not t.get("owns"):
            errs.append(f"{where}: missing owns")
        if not is_command(t.get("verify")):
            errs.append(f"{where}: missing verify (an exact command, not a placeholder)")
        if "verify_baseline" in t and t["verify_baseline"] != "pass":
            errs.append(f"{where}: verify_baseline may only be `pass` (a refactor or pure-prose change that stays green)")
        if t.get("status", "todo") not in STATUSES:
            errs.append(f"{where}: status must be one of {', '.join(STATUSES)}")
        for d in deps[tid]:
            if d not in tids:
                errs.append(f"{where}: depends_on unknown track {d}")
        for pattern in as_list(t.get("owns")):
            if not subsumed(str(pattern), story_owns):
                errs.append(f"{where}: owns {pattern} outside the story's owns")
    contracts = [t for t in tracks if t.get("kind") == "contract"]
    for t in tracks:
        if t.get("kind", "track") == "track" and contracts:
            needs = {str(c.get("id")) for c in contracts}
            if not needs & (set(deps[str(t.get("id"))]) | ancestors(str(t.get("id")), deps)):
                errs.append(f"story {sid} track {t.get('id')}: does not depend on the contract")
    story_acs = {str(a) for a in as_list(story.get("acs"))}
    tasks = as_list(story.get("tasks"))
    task_track = {str(k.get("id")): str(k.get("track")) for k in tasks}
    track_anc = {tid: ancestors(tid, deps) for tid in tids} if tids else {}
    task_ids = [str(k.get("id")) for k in tasks]
    dup_tasks = sorted({k for k in task_ids if task_ids.count(k) > 1})
    if dup_tasks:
        errs.append(f"story {sid}: duplicate task ids {dup_tasks}")
    traced = set()
    for task in as_list(story.get("tasks")):
        kid = str(task.get("id"))
        where = f"story {sid} task {kid}"
        if str(task.get("track")) not in tids:
            errs.append(f"{where}: track {task.get('track')} does not exist")
        if not task.get("do"):
            errs.append(f"{where}: missing do")
        if not is_command(task.get("verify")):
            errs.append(f"{where}: missing verify (an exact command, not a placeholder)")
        mine = str(task.get("track"))
        for d in map(str, as_list(task.get("depends_on"))):
            if d not in task_track:
                errs.append(f"{where}: depends_on unknown task {d}")
            elif task_track[d] != mine and task_track[d] not in track_anc.get(mine, set()):
                errs.append(f"{where}: depends_on {d} in track {task_track[d]}, which track {mine} "
                            "does not wait for (it would block forever)")
        task_acs = {str(a) for a in as_list(task.get("acs"))}
        if task_acs - story_acs:
            errs.append(f"{where}: unknown acs {sorted(task_acs - story_acs)}")
        traced |= task_acs
        track = next((t for t in tracks if str(t.get("id")) == str(task.get("track"))), None)
        for f in as_list(task.get("files")):
            if track and not covered_by(str(f), as_list(track.get("owns"))):
                errs.append(f"{where}: file {f} is outside track {track.get('id')} owns")
    if story.get("tasks") and story_acs - traced:
        errs.append(f"story {sid}: acs with no task: {sorted(story_acs - traced)}")
    integ = story.get("integration") or {}
    if len(tracks) > 1:
        if not integ.get("verify"):
            errs.append(f"story {sid}: integration.verify missing (more than one track)")
        order = [str(x) for x in as_list(integ.get("merge_order"))]
        if order and sorted(order) != sorted(tids):
            errs.append(f"story {sid}: integration.merge_order must list every track once")
        elif order:
            for i, tid in enumerate(order):
                late = [d for d in deps.get(tid, []) if d in order[i + 1:]]
                if late:
                    errs.append(f"story {sid}: integration.merge_order merges {tid} before {', '.join(late)}, "
                                "which it depends on")
    try:
        topo_levels(tids, deps, f"story {sid} tracks")
    except PlanError as exc:
        errs.append(str(exc))
        return errs
    errs += parallel_conflicts({i: as_list(t.get("owns")) for i, t in zip(tids, tracks)},
                               deps, f"story {sid} tracks")
    return errs


def parallel_conflicts(owns: dict[str, list], deps: dict[str, list[str]], what: str) -> list[str]:
    """Units with no dependency path between them must not own overlapping paths."""
    errs = []
    ids = sorted(owns)
    anc = {i: ancestors(i, deps) for i in ids}
    for x, a in enumerate(ids):
        for b in ids[x + 1:]:
            if a in anc[b] or b in anc[a]:
                continue
            hits = overlaps(owns[a], owns[b])
            if hits:
                pairs = ", ".join(f"{p} ~ {q}" for p, q in hits)
                errs.append(f"{what}: {a} and {b} can run in parallel but both own {pairs}")
    return errs


def validate_set(epic: dict | None, stories: list[dict]) -> list[str]:
    errs = validate_epic(epic) if epic else []
    for s in stories:
        errs += validate_story(s)
    if epic:
        entries = {str(s.get("id")): s for s in as_list(epic.get("stories"))}
        for s in stories:
            sid = story_key(s)
            entry = entries.get(sid)
            if entry is None:
                errs.append(f"story {sid}: not in the epic's stories")
                continue
            # A story plan's own consumes must also stay inside its upstreams' owns.
            errs += validate_consumes(f"story {sid}", s, {i: as_list(e.get("owns")) for i, e in entries.items()})
            # The epic is what keeps parallel stories apart, so a story may
            # narrow its entry but never widen it or change its ordering.
            epic_owns = as_list(entry.get("owns"))
            for pattern in as_list(s.get("owns")):
                if not subsumed(str(pattern), epic_owns):
                    errs.append(f"story {sid}: owns {pattern}, which the epic's entry for {sid} does not "
                                "(widen the epic plan first, then re-validate)")
            mine = sorted(map(str, as_list(s.get("depends_on"))))
            theirs = sorted(map(str, as_list(entry.get("depends_on"))))
            if mine != theirs:
                errs.append(f"story {sid}: depends_on {mine} differs from the epic's {theirs}")
    return list(dict.fromkeys(errs))  # story and set checks can report the same edge


# ── scheduling ───────────────────────────────────────────────────────────────

def units(epic: dict | None, stories: list[dict]) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Every track across the given stories as `<story>/<track>`, with dependencies.

    A story that depends on another story waits for all of that story's tracks
    (its integration); a story with no plan yet blocks its dependants.
    """
    by_story = {story_key(s): s for s in stories}
    story_deps: dict[str, list[str]] = {}
    if epic:
        for s in as_list(epic.get("stories")):
            story_deps[str(s.get("id"))] = [str(d) for d in as_list(s.get("depends_on"))]
    for s in stories:
        story_deps.setdefault(story_key(s), [str(d) for d in as_list(s.get("depends_on"))])
    nodes: dict[str, dict] = {}
    deps: dict[str, list[str]] = {}
    for sid, s in by_story.items():
        for t in as_list(s.get("tracks")):
            uid = f"{sid}/{t.get('id')}"
            nodes[uid] = {"story": sid, "track": t, "plan": s}
            deps[uid] = [f"{sid}/{d}" for d in as_list(t.get("depends_on"))]
            for upstream in story_deps.get(sid, []):
                up = by_story.get(upstream)
                if up is None:
                    deps[uid].append(f"{upstream}/<unplanned>")
                else:
                    deps[uid] += [f"{upstream}/{ut.get('id')}" for ut in as_list(up.get("tracks"))]
    return nodes, deps


def next_runnable(epic: dict | None, stories: list[dict], limit: int) -> list[dict]:
    if limit <= 0:
        return []
    nodes, deps = units(epic, stories)
    status = {u: n["track"].get("status", "todo") for u, n in nodes.items()}
    running = [u for u, s in status.items() if s == "running"]
    picked: list[str] = []
    for uid in sorted(nodes):
        if status[uid] != "todo":
            continue
        if any(status.get(d) != "done" for d in deps[uid]):
            continue
        owns = as_list(nodes[uid]["track"].get("owns"))
        if any(overlaps(owns, as_list(nodes[o]["track"].get("owns"))) for o in running + picked):
            continue
        picked.append(uid)
        if len(picked) >= limit:
            break
    out = []
    for uid in picked:
        n = nodes[uid]
        t = n["track"]
        out.append({
            "unit": uid,
            "story": n["story"],
            "issue": n["plan"].get("issue"),
            "branch": n["plan"].get("branch"),
            "track": t.get("id"),
            "kind": t.get("kind", "track"),
            "owns": as_list(t.get("owns")),
            "verify": t.get("verify"),
            "source": n["plan"].get("_source"),
        })
    return out


# ── rendering ────────────────────────────────────────────────────────────────

def code(value) -> str:
    items = as_list(value)
    return ", ".join(f"`{v}`" for v in items) if items else "—"


def render_epic(epic: dict) -> str:
    stories = as_list(epic.get("stories"))
    ids = [str(s.get("id")) for s in stories]
    deps = {str(s.get("id")): [str(d) for d in as_list(s.get("depends_on"))] for s in stories}
    levels = topo_levels(ids, deps, "stories")
    wave = {sid: n + 1 for n, level in enumerate(levels) for sid in level}
    lines = ["**Stories (dependency order)**", "",
             "| ID | Issue | Story | Size | Priority | Wave | Depends on | Owns | ACs |",
             "|----|-------|-------|------|----------|------|------------|------|-----|"]
    for sid in [s for level in levels for s in level]:
        s = next(x for x in stories if str(x.get("id")) == sid)
        lines.append(f"| {sid} | {s.get('issue', '#TBD')} | {s.get('title', '')} | {s.get('size', '')} | "
                     f"{s.get('priority', '')} | {wave[sid]} | {', '.join(deps[sid]) or '—'} | "
                     f"{code(s.get('owns'))} | {', '.join(map(str, as_list(s.get('acs')))) or s.get('constraint', '')} |")
    lines += ["", "**Parallelization map**", ""]
    contracts = as_list(epic.get("contracts"))
    if contracts:
        for c in contracts:
            lines.append(f"- **Shared contract {c.get('id')}:** {c.get('what', '')} — owner {c.get('owner')}, "
                         f"{code(c.get('paths'))}")
    else:
        lines.append("- **Shared contract:** none")
    for n, level in enumerate(levels):
        after = "" if n == 0 else f", after Wave {n}"
        lines.append(f"- **Wave {n + 1} (parallel{after}):** {', '.join(level)}")
    return "\n".join(lines)


def render_story(story: dict) -> str:
    tracks = as_list(story.get("tracks"))
    tids = [str(t.get("id")) for t in tracks]
    deps = {str(t.get("id")): [str(d) for d in as_list(t.get("depends_on"))] for t in tracks}
    levels = topo_levels(tids, deps, "tracks")
    par = {}
    anc = {i: ancestors(i, deps) for i in tids}
    for a in tids:
        par[a] = [b for b in tids if b != a and a not in anc[b] and b not in anc[a]]
    lines = ["**Parallelization**", "",
             "| Track | Kind | Owns | Depends on | Parallel with | Verify | Status |",
             "|-------|------|------|------------|---------------|--------|--------|"]
    for tid in [t for level in levels for t in level]:
        t = next(x for x in tracks if str(x.get("id")) == tid)
        name = f"{tid} — {t['name']}" if t.get("name") else tid
        lines.append(f"| {name} | {t.get('kind', 'track')} | {code(t.get('owns'))} | "
                     f"{', '.join(deps[tid]) or '—'} | {', '.join(par[tid]) or '—'} | "
                     f"`{t.get('verify', '')}` | {t.get('status', 'todo')} |")
    integ = story.get("integration") or {}
    if integ:
        order = " → ".join(map(str, as_list(integ.get("merge_order")))) or "—"
        lines += ["", f"- **Integration:** merge {order}, then `{integ.get('verify', '')}`"]
    tasks = as_list(story.get("tasks"))
    if tasks:
        lines += ["", "**Tasks**", ""]
        for tid in [t for level in levels for t in level]:
            mine = [k for k in tasks if str(k.get("track")) == tid]
            if not mine:
                continue
            lines.append(f"_{tid}_")
            for k in mine:
                done = "x" if next(t for t in tracks if str(t.get("id")) == tid).get("status") == "done" else " "
                extra = []
                if k.get("files"):
                    extra.append(f"files {code(k.get('files'))}")
                if k.get("depends_on"):
                    extra.append(f"after {', '.join(map(str, as_list(k.get('depends_on'))))}")
                if k.get("acs"):
                    extra.append(", ".join(map(str, as_list(k.get("acs")))))
                extra.append(f"verify `{k.get('verify', '')}`")
                lines.append(f"- [{done}] **{k.get('id')}** — {k.get('do', '')} — {' — '.join(extra)}")
            lines.append("")
    return "\n".join(lines).rstrip()


def render(plan: dict) -> str:
    body = render_epic(plan) if plan.get("kind") == "epic" else render_story(plan)
    return f"{GEN_START}\n{body}\n{GEN_END}"


def sync(text: str, plan: dict) -> str:
    """Replace the generated section, or insert it just before the plan block."""
    block = render(plan)
    pattern = re.compile(re.escape(GEN_START) + r".*?" + re.escape(GEN_END), re.DOTALL)
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    m = FENCE.search(text)
    if not m:
        raise PlanError("no agent-plan block to anchor the generated section")
    return text[: m.start()] + block + "\n\n" + text[m.start():]


def _edit_track_fields(block: str, track: str, fields: dict[str, str]) -> str | None:
    """Rewrite only `fields` of one block-style track entry, leaving every other
    line (comments, quoting, ordering) as written. None if the layout isn't the
    plain `- id: <track>` form this understands."""
    lines = block.split("\n")
    start = next((i for i, l in enumerate(lines)
                  if re.match(rf"^(\s*)- id:\s*['\"]?{re.escape(track)}['\"]?\s*(#.*)?$", l)), None)
    if start is None:
        return None
    dash = len(lines[start]) - len(lines[start].lstrip())
    key_indent = dash + 2
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and (len(line) - len(line.lstrip())) <= dash:
            break  # the next entry, or the end of the tracks list
        end += 1
    item = lines[start:end]
    for key, value in fields.items():
        rendered = " " * key_indent + f"{key}: {json.dumps(value, ensure_ascii=False)}"
        at = next((i for i, l in enumerate(item)
                   if re.match(rf"^ {{{key_indent}}}{key}:", l)), None)
        if at is None:
            item.insert(len(item) - next((k for k, l in enumerate(reversed(item)) if l.strip()), 0), rendered)
            continue
        stop = at + 1  # drop continuation lines of a multi-line value
        while stop < len(item) and item[stop].strip() and len(item[stop]) - len(item[stop].lstrip()) > key_indent:
            stop += 1
        item[at:stop] = [rendered]
    return "\n".join(lines[:start] + item + lines[end:])


def set_status(text: str, track: str, status: str, note: str | None) -> str:
    m = FENCE.search(text)
    if not m:
        raise PlanError("no agent-plan block")
    plan = yaml.safe_load(m.group(1))
    hit = next((t for t in as_list(plan.get("tracks")) if str(t.get("id")) == track), None)
    if hit is None:
        raise PlanError(f"no track {track}")
    fields = {"status": status, **({"note": note} if note else {})}
    block = _edit_track_fields(m.group(1), track, fields)
    if block is not None:  # check the edit says what we meant before trusting it
        try:
            edited = yaml.safe_load(block)
            got = next(t for t in as_list(edited.get("tracks")) if str(t.get("id")) == track)
            if any(got.get(k) != v for k, v in fields.items()):
                block = None
        except (yaml.YAMLError, StopIteration, AttributeError):
            block = None
    if block is None:  # unfamiliar layout: re-dump the block (loses comments)
        hit.update(fields)
        block = dump(plan)
    new = text[: m.start(1)] + block + text[m.end(1):]
    return sync(new, extract(new))


# ── learned constraints ──────────────────────────────────────────────────────

CONSTRAINTS_FILE = ".agents/plan-constraints.yaml"


def default_constraints_path() -> str:
    """The constraints file at the repository root (or the working directory)."""
    import subprocess
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    except OSError:
        top = ""
    return str(Path(top or ".") / CONSTRAINTS_FILE)


def load_constraints(path: str) -> list[dict]:
    """Lessons from earlier runs: `constraints: [{paths, constraint, source, date}]`.
    A missing file means none yet."""
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PlanError(f"{path}: plan-constraints is not valid YAML: {exc}") from exc
    except OSError as exc:
        raise PlanError(f"{path}: cannot read plan-constraints: {exc.strerror}") from exc
    items = data.get("constraints") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise PlanError(f"{path}: plan-constraints needs a top-level `constraints:` list")
    for i, c in enumerate(items):
        if not (isinstance(c, dict) and isinstance(c.get("paths"), list) and c["paths"]
                and all(isinstance(x, str) and x.strip() for x in c["paths"])
                and isinstance(c.get("constraint"), str)
                and c["constraint"].strip()):
            raise PlanError(f"{path}: plan-constraints entry {i} needs `paths: [globs]` and `constraint: text`")
    return items


def constraints_for(owns: list, constraints: list[dict]) -> list[dict]:
    """The lessons whose paths overlap what a unit owns."""
    owned = [str(o) for o in as_list(owns)]
    return [c for c in constraints if any(patterns_meet(o, str(g)) for o in owned for g in c["paths"])]


def lesson_line(c: dict) -> str:
    where = ", ".join(f"`{p}`" for p in c["paths"])
    origin = ", ".join(str(x) for x in (c.get("source"), c.get("date")) if x)
    return f"- {c['constraint'].strip()} (applies to {where}{'; from ' + origin if origin else ''})"


# ── briefs ───────────────────────────────────────────────────────────────────

def brief(story: dict, track_id: str, constraints: list[dict] | None = None) -> str:
    tracks = as_list(story.get("tracks"))
    t = next((x for x in tracks if str(x.get("id")) == track_id), None)
    if t is None:
        raise PlanError(f"no track {track_id} in story {story_key(story)}")
    others = [x for x in tracks if x is not t]
    forbidden = sorted({p for x in others for p in as_list(x.get("owns"))} | set(map(str, as_list(story.get("must_not_touch")))))
    tasks = [k for k in as_list(story.get("tasks")) if str(k.get("track")) == track_id]
    contract = next((x for x in tracks if x.get("kind") == "contract"), None)
    lines = [
        f"# Track {track_id} of story {story_key(story)} ({story.get('issue', 'no issue')})",
        "",
        "You are implementing one track of a parallel plan. Other agents are working on the",
        "other tracks at the same time, in other worktrees, so stay inside your paths.",
        "",
        "## Scope",
        f"- **You may change:** {code(t.get('owns'))}",
        f"- **Do not change:** {code(forbidden) if forbidden else 'anything outside the paths above'}",
        f"- **Done when:** `{t.get('verify')}` passes and every task below is complete.",
    ]
    if contract is not None and contract is not t:
        lines.append(f"- **Shared contract (already merged, read-only):** {code(contract.get('owns'))}")
    reads = ([str(x) for items in t["consumes"].values() for x in as_list(items)]
             if isinstance(t.get("consumes"), dict) else [])
    if reads:
        lines.append(f"- **You read from upstream (merged first, read-only):** {code(reads)}")
    context = t.get("context") or story.get("context")
    if context:
        lines += ["", "## Context", str(context).strip()]
    learned = constraints_for(as_list(t.get("owns")), constraints or [])
    if learned:
        lines += ["", "## Lessons from earlier runs",
                  "Confirmed causes of past failures in the paths you own. Follow them:"]
        lines += [lesson_line(c) for c in learned]
    acs = story.get("ac_text") or {}
    task_acs = sorted({str(a) for k in tasks for a in as_list(k.get("acs"))})
    if not tasks:
        task_acs = [str(a) for a in as_list(story.get("acs"))]
    if task_acs:
        lines += ["", "## Acceptance criteria you serve"]
        for a in task_acs:
            lines.append(f"- **{a}:** {acs.get(a, '(see the story issue)')}")
    lines += ["", "## Tasks (in order)"]
    for k in tasks:
        lines.append(f"- [ ] **{k.get('id')}** — {k.get('do')} (verify: `{k.get('verify')}`)")
        if k.get("files"):
            lines.append(f"      files: {code(k.get('files'))}")
    if not tasks:
        lines.append("- Implement the track as described in the story; keep to the scope above.")
    lines += [
        "",
        "## Rules",
        "- Commit on your branch with Conventional Commits; do not push or merge.",
        "- If the work needs a path you do not own, stop and report it instead of editing it.",
        "- If the contract is wrong or missing something, stop and report; do not change it.",
        "- Write or update tests for what you change, then run the verify command.",
        "",
        "## Report back",
        "Reply with: status (done | blocked), the commits you made, the verify output",
        "(last lines), and anything the integrator must know.",
    ]
    return "\n".join(lines)


# ── check: everything a planner runs before handing a plan on ──────────────

def _validate_artifact():
    import importlib.util
    spec = importlib.util.spec_from_file_location("validate_artifact", Path(__file__).with_name("validate_artifact.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def check(paths: list[str], write: bool = True,
          constraints: list[dict] | None = None) -> tuple[bool, list[str]]:
    """Validate the plan set, re-sync generated tables, check each body's prose
    shape, and summarize the waves. Returns (ok, report lines)."""
    lines: list[str] = []
    buffered = {path: read_text(path) for path in paths if path == "-"}
    epic, stories = load(paths, buffered)
    errs = validate_set(epic, stories)
    lines += [f"FAIL plan: {e}" for e in errs]
    va = _validate_artifact()
    for path in paths:
        text = buffered[path] if path in buffered else read_text(path)
        plan = extract(text, path)
        if write and not errs and path != "-":
            new = sync(text, plan)
            if new != text:
                Path(path).write_text(new, encoding="utf-8")
                lines.append(f"synced {path}")
                text = new
        shape = va.check_epic(text) if plan.get("kind") == "epic" else va.check_story(text)
        lines += [f"FAIL shape {path}: {e}" for e in shape]
        errs += shape
    if not errs:
        if epic:
            ss = as_list(epic.get("stories"))
            deps = {str(x.get("id")): [str(d) for d in as_list(x.get("depends_on"))] for x in ss}
            for n, level in enumerate(topo_levels(list(deps), deps, "stories")):
                lines.append(f"stories wave {n + 1}: {', '.join(level)}")
        nodes, deps = units(epic, stories)
        if nodes:
            for n, level in enumerate(topo_levels(list(nodes), deps, "tracks")):
                lines.append(f"tracks wave {n + 1}: {', '.join(level)}")
            waiting = waiting_on_unplanned(list(nodes), deps)
            if waiting:
                lines.append(f"tracks waiting on unplanned stories: {', '.join(waiting)}")
        lines += [f"WARN edge: {w}" for w in edge_warnings(epic, stories)]
        planned = ([(str(s.get("id")), as_list(s.get("owns"))) for s in as_list(epic.get("stories"))] if epic
                   else [(story_key(s), as_list(s.get("owns"))) for s in stories])
        for sid, owns in planned:  # apply these when splitting or tracking the story
            lines += [f"LEARNED {sid}: {c['constraint'].strip()} (from {c.get('source', 'an earlier run')})"
                      for c in constraints_for(owns, constraints or [])]
        n_tracks = sum(len(as_list(x.get("tracks"))) for x in stories)
        lines.append(f"PASS: {'epic + ' if epic else ''}{len(stories)} stories, {n_tracks} tracks")
    return not errs, lines


# ── scaffold: story skeletons from the epic plan ─────────────────────────────

BRANCH_TYPE = {"user": "feat", "technical": "feat", "bug": "fix", "spike": "spike"}
EPIC_AC_LINE = re.compile(r"^\s*[-*]\s*\*\*(AC\d+):?\*\*:?\s*(.+)$", re.MULTILINE)


def slug(text: str, words: int = 5) -> str:
    parts = re.findall(r"[a-z0-9]+", str(text).lower())
    return "-".join(parts[:words]) or "story"


def issue_number(ref) -> str | None:
    m = re.fullmatch(r"#?(\d+)", str(ref or "").strip())
    return m.group(1) if m else None


def branch_name(entry: dict) -> str:
    kind = BRANCH_TYPE.get(str(entry.get("type", "user")), "feat")
    num = issue_number(entry.get("issue")) or str(entry.get("id")).lower()
    return f"{kind}/{num}-{slug(entry.get('title', ''))}"


def parallel_peers(epic: dict) -> dict[str, list[str]]:
    """For each story, the stories that can run at the same time as it."""
    ss = as_list(epic.get("stories"))
    ids = [str(x.get("id")) for x in ss]
    deps = {str(x.get("id")): [str(d) for d in as_list(x.get("depends_on"))] for x in ss}
    anc = {i: ancestors(i, deps) for i in ids}
    return {a: [b for b in ids if b != a and a not in anc[b] and b not in anc[a]] for a in ids}


def scaffold(epic_text: str, template: str, only: list[str] | None = None) -> dict[str, str]:
    """Story bodies keyed by story id: the template's prose with the plan block
    filled from the epic (ids, ACs, ownership, dependencies, verify, branch, and
    must_not_touch = what parallel stories own) and one default track. The
    planner then writes context, Given/When/Then criteria and real tracks."""
    epic = extract(epic_text, "epic")
    if epic.get("kind") != "epic":
        raise PlanError("scaffold needs an epic plan")
    errs = validate_epic(epic)
    if errs:
        raise PlanError("the epic plan does not validate: " + "; ".join(errs))
    ac_prose = dict(EPIC_AC_LINE.findall(epic_text))
    peers = parallel_peers(epic)
    entries = {str(x.get("id")): x for x in as_list(epic.get("stories"))}
    unknown = sorted(set(only or []) - set(entries))
    if unknown:
        raise PlanError(f"--stories names no such story in the epic: {', '.join(unknown)}")
    out = {}
    for sid, entry in entries.items():
        if only and sid not in only:
            continue
        owns = as_list(entry.get("owns"))
        forbidden = sorted({str(p) for peer in peers[sid] for p in as_list(entries[peer].get("owns"))})
        block = {
            "version": 1,
            "kind": "story",
            "story": sid,
            "epic": epic.get("epic", "#TBD"),
            "issue": entry.get("issue", "#TBD"),
            "branch": branch_name(entry),
            "acs": as_list(entry.get("acs")),
            "ac_text": {a: ac_prose.get(a, "") for a in as_list(entry.get("acs"))},
            "depends_on": as_list(entry.get("depends_on")),
            **({"consumes": entry["consumes"]} if entry.get("consumes") else {}),
            "owns": owns,
            "must_not_touch": forbidden,
            "verify": entry.get("verify"),
            "context": "",
            "tracks": [{"id": "main", "kind": "track", "owns": owns, "verify": entry.get("verify")}],
        }
        if entry.get("constraint"):
            block["constraint"] = entry["constraint"]
        if not block["acs"]:
            del block["ac_text"]
        body = template
        body = re.sub(r"\A<!--.*?-->\s*", "", body, flags=re.DOTALL)
        body = body.replace("Part of #<epic> · Story S<n>",
                            f"Part of {block['epic']} · Story {sid} — {entry.get('title', '')}")
        dumped = dump(block)
        body = FENCE.sub(lambda _: "```yaml agent-plan\n" + dumped + "```", body, count=1)
        if not FENCE.search(body):
            body = body.rstrip() + "\n\n```yaml agent-plan\n" + dumped + "```\n"
        out[sid] = sync(body, block)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Read, check and schedule agent-plan blocks.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract"); p.add_argument("file"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("validate"); p.add_argument("files", nargs="+")
    p = sub.add_parser("waves"); p.add_argument("files", nargs="+")
    p = sub.add_parser("render"); p.add_argument("file")
    p = sub.add_parser("sync"); p.add_argument("file")
    p = sub.add_parser("next"); p.add_argument("files", nargs="+"); p.add_argument("--max", type=int, default=4)
    p = sub.add_parser("brief"); p.add_argument("file"); p.add_argument("--track", required=True)
    p.add_argument("--constraints", help=f"lessons file (default: <repo>/{CONSTRAINTS_FILE})")
    p = sub.add_parser("scope"); p.add_argument("file"); p.add_argument("--track", required=True)
    p.add_argument("--changed", nargs="*", default=[])
    p = sub.add_parser("check"); p.add_argument("files", nargs="+"); p.add_argument("--no-sync", action="store_true")
    p.add_argument("--constraints", help=f"lessons file (default: <repo>/{CONSTRAINTS_FILE})")
    p = sub.add_parser("scaffold"); p.add_argument("epic"); p.add_argument("--out", default=".")
    p.add_argument("--stories", help="comma-separated story ids (default: all)")
    p.add_argument("--template", default=str(Path(__file__).resolve().parents[1] / "templates" / "epic" / "story-shell.md"))
    p.add_argument("--force", action="store_true", help="overwrite existing story files")
    p = sub.add_parser("status"); p.add_argument("file"); p.add_argument("--track", required=True)
    p.add_argument("--set", dest="value", choices=STATUSES, required=True); p.add_argument("--note")
    args = ap.parse_args()

    rewrites = {"sync": [getattr(args, "file", None)], "status": [getattr(args, "file", None)],
                "check": [] if getattr(args, "no_sync", True) else getattr(args, "files", [])}
    if "-" in rewrites.get(args.cmd, []):
        print(f"error: {args.cmd} rewrites its input, which can't be stdin; pass a file", file=sys.stderr)
        return 2

    try:
        if args.cmd == "extract":
            plan = extract(read_text(args.file), args.file)
            print(json.dumps(plan, indent=2) if args.json else yaml.safe_dump(plan, sort_keys=False), end="")
            return 0
        if args.cmd == "validate":
            epic, stories = load(args.files)
            errs = validate_set(epic, stories)
            for e in errs:
                print(f"FAIL: {e}", file=sys.stderr)
            if errs:
                return 1
            n_tracks = sum(len(as_list(s.get("tracks"))) for s in stories)
            print(f"PASS: {'epic + ' if epic else ''}{len(stories)} stories, {n_tracks} tracks")
            return 0
        if args.cmd == "waves":
            epic, stories = load(args.files)
            if epic:
                ss = as_list(epic.get("stories"))
                deps = {str(s.get("id")): [str(d) for d in as_list(s.get("depends_on"))] for s in ss}
                for n, level in enumerate(topo_levels(list(deps), deps, "stories")):
                    print(f"stories wave {n + 1}: {', '.join(level)}")
            nodes, deps = units(epic, stories)
            if nodes:
                for n, level in enumerate(topo_levels(list(nodes), deps, "tracks")):
                    print(f"tracks wave {n + 1}: {', '.join(level)}")
                waiting = waiting_on_unplanned(list(nodes), deps)
                if waiting:
                    print(f"tracks waiting on unplanned stories: {', '.join(waiting)}")
            return 0
        if args.cmd == "render":
            print(render(extract(read_text(args.file), args.file)))
            return 0
        if args.cmd == "sync":
            text = read_text(args.file)
            Path(args.file).write_text(sync(text, extract(text, args.file)), encoding="utf-8")
            print(f"synced {args.file}")
            return 0
        if args.cmd == "next":
            epic, stories = load(args.files)
            errs = validate_set(epic, stories)
            if errs:
                for e in errs:
                    print(f"FAIL: {e}", file=sys.stderr)
                return 1
            print(json.dumps(next_runnable(epic, stories, args.max), indent=2))
            return 0
        if args.cmd == "brief":
            print(brief(extract(read_text(args.file), args.file), args.track,
                        load_constraints(args.constraints or default_constraints_path())))
            return 0
        if args.cmd == "scope":
            story = extract(read_text(args.file), args.file)
            t = next((x for x in as_list(story.get("tracks")) if str(x.get("id")) == args.track), None)
            if t is None:
                raise PlanError(f"no track {args.track}")
            outside = [c for c in args.changed if not covered_by(c, as_list(t.get("owns")))]
            for c in outside:
                print(f"FAIL: {c} is outside track {args.track} owns {as_list(t.get('owns'))}", file=sys.stderr)
            if outside:
                return 1
            print(f"PASS: {len(args.changed)} changed paths inside track {args.track}")
            return 0
        if args.cmd == "check":
            ok, lines = check(args.files, write=not args.no_sync,
                              constraints=load_constraints(args.constraints or default_constraints_path()))
            for line in lines:
                print(line, file=sys.stdout if ok or not line.startswith("FAIL") else sys.stderr)
            return 0 if ok else 1
        if args.cmd == "scaffold":
            only = [x.strip() for x in args.stories.split(",")] if args.stories else None
            bodies = scaffold(read_text(args.epic), read_text(args.template), only)
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            for sid, body in bodies.items():
                dst = out / f"story-{sid}.md"
                if dst.exists() and not args.force:
                    print(f"kept {dst} (exists; --force to replace)")
                    continue
                dst.write_text(body, encoding="utf-8")
                print(f"wrote {dst}")
            return 0
        if args.cmd == "status":
            text = read_text(args.file)
            Path(args.file).write_text(set_status(text, args.track, args.value, args.note), encoding="utf-8")
            print(f"{args.track} -> {args.value}")
            return 0
    except PlanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
