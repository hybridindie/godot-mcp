<!--
  agent-plan-schema.md — the machine-readable plan carried by Epic and story issues
  Referenced by: epic-composer, story-decomposer, task-decomposer, wave-dispatcher
  version: 1.8.0, owner: John D
  Single source of truth for the `agent-plan` block. `.agents/scripts/plan.py`
  enforces it; skills write it; the dispatcher schedules from it.
-->

# The `agent-plan` block

Every Epic and story issue ends with **one** fenced block that agents read
instead of the prose. The shells wrap it in
`<details><summary>agent-plan (machine-readable)</summary> … </details>` so the
rendered issue stays readable; the wrapper is presentation only. `plan.py`
extracts the fence wherever it sits and `sync` leaves the wrapper in place:

````markdown
```yaml agent-plan
version: 1
kind: story
...
```
````

People read the issue; agents read the block. The tables people see (story map,
parallelization, task checklist) are **generated** from the block by
`plan.py sync` and sit between `<!-- agent-plan:generated -->` markers — never
hand-edit them, edit the block and re-sync. Waves are **computed** from
`depends_on`, never written down, so they cannot drift.

## Why it looks like this

- **One owner per path at a time.** Two units that can run at the same time
  (no `depends_on` path between them) must own disjoint paths. This is what lets
  a lead hand units to parallel subagents without merge conflicts, and
  `plan.py validate` rejects plans that break it.
- **Every unit proves itself.** `verify` is an exact command a subagent runs
  before reporting done. "Tests pass" is not a command.
- **Everything traces.** Stories trace to Epic ACs, tasks to story ACs, so
  coverage gaps show up as validation errors instead of surprises.

## Epic block

```yaml agent-plan
version: 1
kind: epic
epic: "#12"                 # this issue, once created ("#TBD" before)
acs: [AC1, AC2, AC3]        # labels of the 3–8 ACs in the prose above
contracts:                  # shared interfaces between stories; [] if none
  - id: C1
    what: ExportJob response schema
    owner: S1               # the story that lands it
    paths: [backend/export/schema.py]
stories:
  - id: S1                  # stable id; issue numbers come later
    title: Export API returns a PDF job
    issue: "#TBD"
    type: user              # user | spike | technical | bug
    size: M                 # S | M | L (≤ ~3 days); split anything larger
    priority: P0            # P0 | P1 | P2
    acs: [AC1]              # or `constraint: <reason>` for enabling work
    depends_on: []          # story ids whose output this story needs
    # consumes:             # what crosses each edge: upstream paths (or path::Symbol)
    #   S0: [backend/auth/session.py::current_user]
    owns: [backend/export/**]
    verify: uv run pytest tests/export -q
    status: todo            # todo | running | done | blocked
```

## Story block

```yaml agent-plan
version: 1
kind: story
story: S1                   # the id from the Epic block
epic: "#12"
issue: "#13"
branch: feat/13-export-api  # integration branch the tracks merge into
acs: [AC1]
ac_text:                    # copied into subagent briefs
  AC1: Given a report under 500 rows, when export is requested, then …
depends_on: []              # story ids (same as the Epic's)
owns: [backend/export/**, tests/export/**]
must_not_touch: [frontend/**]
verify: uv run pytest tests/export -q        # story-level end-to-end check
# ship: per-track           # optional: one stacked PR per track (see "Size a story to one PR")
context: >-                 # what a subagent with no other context must know
  The export pipeline is synchronous today; this adds a job API.
tracks:                     # one track = one subagent in one worktree
  - id: contract
    kind: contract          # lands first; every other track depends on it
    owns: [backend/export/schema.py]
    verify: uv run python -c "import backend.export.schema"
    status: todo
  - id: A
    name: API route
    kind: track
    owns: [backend/export/routes.py, tests/export/test_routes.py]
    depends_on: [contract]
    consumes:
      contract: [backend/export/schema.py::ExportJob]
    verify: uv run pytest tests/export/test_routes.py -q
    # optional: replaces the story context in this track's brief, for when
    # the story context mentions work this track must not do
    context: Add the route only; the PDF worker is track B.
    # optional, refactors only: verify already passes and must stay green
    # verify_baseline: pass
    # optional: contained | wide | irreversible (see "Merge lanes")
    # lane: irreversible
    status: todo
tasks:                      # written by task-decomposer; PR-sized steps
  - id: T1
    track: contract
    do: Define ExportJob in backend/export/schema.py (new)
    files: [backend/export/schema.py]
    verify: uv run python -c "import backend.export.schema"
    acs: [AC1]
integration:
  merge_order: [contract, A]
  verify: uv run pytest tests/export -q
```

A story without `tasks` is still dispatchable: the subagent works from the
track and the story's context. Add tasks when a track is more than one obvious
change.

## Writing rules

- **Block style for anything with punctuation.** Use one key per line for
  tasks. Inline `{…}` mappings break on `{id}`, `:` or `#` inside values; quote
  a value that contains `: `, ` #`, `{` or starts with `*`, `&`, `!` or `@`.
- **Paths are repo-relative globs.** `src/api/**` (or just `src/api`) for a
  tree, an exact path for a file, `src/*.py` for files directly in `src/`.
  `**` spans directories; `*` stays within one. A track's `owns` must sit inside
  its story's `owns`.
- **Shared generated files need one owner.** Lockfiles (`uv.lock`,
  `package-lock.json`), a new package's `__init__.py`, and registries such as an
  app's router list change whenever a dependency or module is added. Give each
  to exactly one unit per wave, or sequence the units that need it; dispatch
  rejects a diff that touches a path its track does not own.
- **Verify is a command.** `<command>`, `TBD`, `N/A` and blanks are rejected.
- **Verify must be able to fail.** `dispatch.py prepare` runs each track's
  verify once before work starts. If it already passes, the track is flagged
  as a weak check: its brief asks for a failing test first, and `check`
  rejects a diff that adds or changes no test. A refactor that should stay
  green before and after declares `verify_baseline: pass`.
  A **skill-only track** (a skill body, doctrine or other prose, whose only
  tests are behavioural-eval markdown) needs a check that fails until the new
  behaviour is written: a content assertion such as
  `grep -q 'integrate <story> --sync' .agents/skills/x/SKILL.md`, or a lint
  rule. Behavioural cases are checked for format only, so they cannot go red.
  A pure-prose change with nothing to assert (a rewording) declares
  `verify_baseline: pass` instead.
- **Size a story to one PR.** The integrated story branch is one PR, held to
  the PR budget (≤ 400 changed lines and ≤ 25 files, tests included; see the
  workflow rule and ship-pr's `pr_size.py`). Tracks that each fit can still
  sum past it. Split such a story, or set `ship: per-track` on it (two or
  more tracks): the dispatcher then opens one stacked PR per track in
  `merge_order`. The dispatcher also splits a story that measures over budget
  when it ships.
- **Dependants ship after their upstreams.** A story branch starts from its
  upstreams' work, so its PR would carry their diff too. `dispatch.py
  integrate <story> --sync origin/main` refuses until every `depends_on`
  story is in `origin/main`, then merges it in, so the PR shows only the
  story's own work.
- **Merge lanes follow blast radius, not confidence.** Each track gets a lane
  from what it owns, and the lane decides how its merge is gated:

  | Lane | What it owns | Gate |
  |---|---|---|
  | `irreversible` | anything inside `**/migrations/**`, `**/alembic/**`, `**/*.sql`, `supabase/**`, `deploy/**`, `deployments/**`, `infra/**`, `k8s/**`, `helm/**`, `terraform/**`, `**/*.tf`, or a plan's own `lanes: {irreversible: [...]}` | never auto-merged: `merge` refuses without `--human` |
  | `wide` | a contract track, or a path an Epic contract names | checks plus a diff review |
  | `contained` | everything else | checks |

  `check` also escalates a unit to `irreversible` when its diff touches one of
  those paths, whatever the plan predicted. `lane:` on a track sets it
  explicitly. Irreversible is a closed lane, not a high threshold: ship-pr's
  `merge_pr.py` reads the same globs (plus a repo's
  `merge_policy.irreversible_paths`) and leaves such a PR for a person.
- **Every edge names what crosses it.** A dependency means "I read your
  output", not "and then". Give each `depends_on` entry a `consumes` list of
  the upstream paths (optionally `path::Symbol`) it reads; each must lie inside
  that upstream's `owns`. If you can't name one, there is no edge: drop it and
  let the units run in parallel. `plan.py check` warns on an edge without
  `consumes` (`WARN edge: ...`), and the brief shows the track what it reads.
- **Contracts are tracks.** Inside a story, a shared interface is a track with
  `kind: contract`; across stories it is an Epic `contracts` entry owned by one
  story, and dependants list that story in `depends_on`.
- **Status is written by the dispatcher**, not by planners. New plans use
  `todo` or leave it out.
- **Ids are stable.** Never renumber stories, tracks or tasks after dispatch
  starts; add new ones instead.

## Lessons from earlier runs

A confirmed cause of a failure becomes a constraint that later plans follow,
in `.agents/plan-constraints.yaml` at the repo root:

```yaml
constraints:
  - paths: [backend/app/schedules/models.py]
    constraint: Changing the Schedule model needs frontend/src/schedules/api.ts regenerated in the same story.
    source: S4/api        # the unit whose failure taught it
    date: "2026-11-21"
```

Lessons are recorded automatically from a diagnosis: `dispatch.py escalate
<unit> --diagnosis <file> --lesson-paths <globs> --lesson <text>` appends one
with no approval step, under the rules for a confirmed cause in
[`escalation.md`](escalation.md). `dispatch.py learn` does the same outside an
escalation. Both validate the entry and store a repeated lesson once. The
review happens at the PR: the constraints file is committed with the run and
lands through a reviewed PR like any other change, so a wrong lesson is caught
there, not at the prompt.

`plan.py check` prints `LEARNED <story>: ...` for every constraint whose paths
overlap a story's `owns`, and each brief carries the ones that overlap its
track. The fix for the run you're in is `retry`; a lesson changes every run
after it.

## Commands

```bash
plan=.agents/scripts/plan.py
python3 $plan check    epic.md story-*.md   # validate + regenerate tables + prose shape + waves
python3 $plan scaffold epic.md --out .      # story-<id>.md skeletons with the plan prefilled
python3 $plan next     epic.md story-*.md   # tracks that can start now (JSON)
python3 $plan brief    story.md --track A   # the subagent brief
```

`.agents/scripts/dispatch.py` runs a plan (load, prepare, check, merge, block,
integrate, report); `wave-dispatcher` is the skill that drives it. Both scripts
need PyYAML; without it they re-run themselves under `uv` to fetch it.
