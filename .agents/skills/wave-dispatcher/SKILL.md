---
name: wave-dispatcher
description: >
  Execute a planned Epic or story with parallel subagents: start every track whose
  dependencies are done, each in its own git worktree, check each diff stays inside the
  track's owned paths and passes its verify command, merge into the story branch in
  order, and write progress back to the GitHub or Gitea issue. Trigger phrases:
  "dispatch the next wave", "run this epic", "execute the stories in parallel", "start
  the agents on this plan", "work the epic", "kick off wave 1". Use whenever the user
  wants planned Epic/story work implemented by parallel agents, or asks what can run
  next.
---

# Wave Dispatcher

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 2.9.0, owner: John D
  invokes: .agents/scripts/dispatch.py,
           .agents/scripts/plan.py,
           .agents/scripts/budget.py
  doctrine: .agents/doctrine/agent-plan-schema.md,
            .agents/doctrine/parallelization-doctrine.md,
            .agents/doctrine/escalation.md
-->

Execute a planned Epic or story with parallel subagents. `dispatch.py` does
every mechanical step — loading plans from the issues, branches and worktrees,
the scope and verify checks, merge order, conflicts, status written back to the
issues — and prints JSON. You do the two things a script cannot: run the
subagents, and judge whether each one's work does what its brief asked.

Worktrees make this safe: parallel subagents never share a working tree, so
their work meets only in a `dispatch.py merge` after the checks pass.

## Inputs

- Required: an Epic or story reference (`#12`, URL) or local body files with
  `agent-plan` blocks.
- Optional: `--max N` concurrent subagents (default 3), `--plan` (dry run),
  `--ship` (open each finished story's PR with ship-pr).
- Read: the JSON `dispatch.py` prints, each brief, each subagent's report and
  each finished track's diff.
- Do not read: the code while a subagent is still writing it.

## Deterministic Steps

Run every command from the repository root; `d=".agents/scripts/dispatch.py"`,
`b=".agents/scripts/budget.py"`. **After every subagent finishes** (track,
reviewer or diagnosis), run `python3 $b record --epic <epic> --unit <unit>
--tokens <tokens it reported>`; before each `prepare`, `python3 $b status
--epic <epic>` — on `pause`, start nothing new.

1. **Load.** `python3 $d load --epic <ref>` (or `--story <ref>...`, or
   `--files <paths>` for local bodies). Stop if `ok` is false; report
   `unplanned_stories` — they need story-decomposer before they can run.
2. **Prepare the next wave.** `python3 $d prepare --max <n>`. It refuses a
   dirty checkout, creates each runnable unit's branch and worktree (a story
   that depends on others starts from their finished work), marks it running
   on the issue and writes its brief. It also runs each unit's verify once on
   the untouched worktree: a unit whose verify already passes comes back with
   `weak_check: true`, and its brief asks for a failing test first. With
   `--plan`, run `python3 $d prepare --plan` instead, report the units, their `would_run`
   commands and briefs, and stop. An empty `units` list: go to step 6.
3. **Dispatch in parallel.** In one turn, start one general-purpose subagent
   per unit (Claude Code: the Agent tool; OpenCode: the task tool) whose prompt
   is the unit's brief file, verbatim.
4. **Check each report as it arrives.**
   `python3 $d check <unit>` runs the scope check, the verify command (and
   cleans up what it wrote) and lists commits, findings and the `lane`. For a
   `wide` or `irreversible` unit, read the diff with the `review` command it
   prints, against the brief: every task done, the ACs actually met, and a
   contract track implementing the real contract (a stub or faked result that
   only satisfies a weak test is a finding). Weigh its `history` too: a unit
   that passed on its third attempt, or was restarted after a conflict, gets
   a closer read than one that passed first time. A `wide` unit's review is
   done by a fresh subagent (diff, brief, ACs, `history`; findings only, no
   edits), not by you; its findings feed the fix below.
   - `ok` → merge by the unit's `lane` (it can be stricter than prepare
     said, if the diff touched a migration or deploy path):
     - `contained`: `python3 $d merge <unit>`; the checks are the gate.
     - `wide`: merge once the reviewer subagent's review passes.
     - `irreversible`: never merge it yourself; report it for a person's
       approval (`awaiting_human`), then `python3 $d merge <unit> --human`.
     `merge` enforces `merge_order`, and on a conflict aborts and blocks.
   - Fixable inside the track's paths → `python3 $d retry <unit> --note
     "<what to fix>"`, then start a fresh subagent on the `brief` it prints.
     The worktree and the work that passed are kept; the brief adds the
     findings, the verify output and "fix only these". `check` flags a retry
     that touches files the findings don't name. For a reviewer's findings
     on a passing wide unit, write them to a file (one per line) and run
     `python3 $d retry <unit> --note "<what to fix>" --review-findings
     <file>`: it counts the attempt like any retry (same cap, same
     escalation) and puts the findings in the brief the same way; then
     `check` and review the new attempt.
   - After the third failure (`retry` blocks it, `report` → `needs_replan`),
     do not stop or ask anyone: climb `.agents/doctrine/escalation.md`.
     Start a fresh read-only subagent (no edits, commits or `dispatch.py`)
     with the unit's findings, each attempt's diff, the verify tails and
     `history`; it writes the diagnosis file the doctrine describes. Then run
     `python3 $d escalate <unit> --diagnosis <file> --outcome <rung>` with
     the rung it supports: `attempt` (confirmed, inside `owns`; start a fresh
     subagent on the printed `brief`), `replan` (confirmed, in the plan) or
     `needs-input --question "<what a person must decide>"` (suspected, or
     a person's call; the only rung left once attempt or replan failed). A
     lesson the diagnosis names for a confirmed cause goes on the same call,
     `--lesson "<constraint>" --lesson-paths <globs>`, without asking first.
   - A plan or ownership problem → `python3 $d block <unit> --note "<every
     finding, one clause each>"`. Leave the worktree.
   - A confirmed, recurring cause outside an escalation (say, a schema change
     that always needs a regenerated client): `python3 $d learn --unit <unit>
     --paths <globs> --constraint "<text>"`, commit `.agents/plan-constraints.yaml`.
5. **Loop** to step 2: merged tracks unblock their dependants and the next
   stories. Stop after 10 rounds.
6. **Integrate finished stories.** For each story in
   `python3 $d report` → `stories_ready_to_integrate`:
   `python3 $d integrate <story> --push` (runs the integration and story
   verify commands, pushes on success). With `--ship`, ship a story only
   once every story in its `upstreams` has merged: `git fetch origin`, then
   `integrate <story> --sync origin/main --push` (refuses while an upstream
   is unmerged; merges main in so the PR shows only this story). Measure it
   from its integration worktree with ship-pr's `pr_size.py --base
   origin/main`. Over budget, or `ship: per-track`, open stacked PRs: one
   branch `<story branch>-<track>` per track at its `merged` sha, in
   `merge_order`, each PR based on the previous one; ship-pr them all at
   once and merge with its `merge_stack.py` (merge commits, no rebase). A PR
   left "ready for a person" is `awaiting_human`: never merge it yourself.
7. **Report** from `python3 $d report`; each unit's `history` gives its
   attempts, failed checks, blocks and rollbacks across every run.

## LLM Judgment

Use judgment only for:

- reviewing a wide or irreversible track's diff against its brief and ACs;
- choosing retry (fixable inside the track's paths) or block (a plan or
  ownership problem), and writing that note;
- choosing the escalation outcome the diagnosis supports — a suspected cause
  always goes to `needs-input`.

Do not edit a subagent's code, change ownership, or run the git steps
`dispatch.py` owns by hand — report the failure; the plan gets fixed by
story-decomposer or the human.

## Output

```markdown
Epic: <ref>    Round: <n>    Running: <n>    Done: <n>/<total>    Blocked: <n>

| Unit | Status | Verify | Tries | Rollbacks | Note |
|------|--------|--------|-------|-----------|------|
| S1/contract | done | pass | 2 | 0 | merged abc123 |
| S1/A | blocked | fail | 1 | 1 | 2 tests fail in test_routes.py; edits uv.lock |
| S2/main | blocked | weak | 1 | 0 | verify passed before work; diff adds no test |

Next runnable: <units or none — waiting on …>
Stories integrated: <branches or none>
Blocked worktrees: <paths>
Awaiting a human (irreversible lane): <units or none>
Needs input (escalated): <unit: question, or none>
Budget: <used>/<limit> (<percent>%, <state>)
```

## Stop Conditions

- Stop if `load` or `prepare` reports `ok: false` or an `error`.
- Stop dispatching a story after a merge conflict; other stories continue.
- Stop when nothing is runnable and nothing is running.
- Start nothing new when `budget.py status` says `pause`.
- Never retry a unit a fourth time without an `escalate` call; the ladder
  ends with `needs-input`, never another loop.
- Never push to or merge into the default branch; never force-push.

## Token Budget

- Default: the JSON from `dispatch.py`, the briefs, the subagents' reports, and
  each finished track's diff limited to its owned paths.
- Keep the report to the table above plus one line per blocker, ≤ 300 words.
