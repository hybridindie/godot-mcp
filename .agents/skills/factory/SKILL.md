---
name: factory
description: >
  Run the software factory in this session: take each approved Epic that is open now,
  oldest first, label it factory:running, then decompose it into stories, gate the plan
  with plan-reviewer, decompose tasks, dispatch and ship the waves, with a per-Epic token
  budget and the escalation ladder on every loop. Trigger phrases: "start the factory",
  "run the factory", "work the backlog unattended", "ship the approved epics", "factory mode".
  Use when the user wants approved Epics picked up and shipped without prompting.
---

# Factory

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 2.2.0, owner: John D
  invokes: .agents/scripts/tracker.py,
           .agents/scripts/budget.py,
           .agents/scripts/plan.py,
           .agents/scripts/plan_review.py,
           .agents/scripts/dispatch.py
  skills: story-decomposer, plan-reviewer, task-decomposer, wave-dispatcher
  doctrine: .agents/doctrine/escalation.md
-->

Carry every approved Epic that is open now to shipped PRs, one at a time, then
exit. The factory never waits for new Epics: with none to work, it says so and
stops.
The scripts own every mechanical step and every label; you run the subagents,
read their reports, and decide the rung when a loop runs out. The factory runs
**in this session**, never as a background job or a scheduled cloud agent,
so a person can watch every round and step in.

## Inputs

- Required: nothing; the tracker is found from the `origin` remote.
- Optional: `--limit L` tokens per Epic (passed to `budget.py status`,
  default 5,000,000), `--max N` concurrent subagents (default 3), `--epic #N`
  to run one named Epic and stop.
- Read: the JSON every script prints, issue labels, each subagent's report
  and its reported token count, `.agents/doctrine/escalation.md`.
- Do not read: the code a subagent is still writing.

## Deterministic Steps

From the repository root; `t=".agents/scripts/tracker.py"`,
`b=".agents/scripts/budget.py"`, `d=".agents/scripts/dispatch.py"`.
**Labels** are only ever set with `python3 $t label <ref> --add/--remove`.

1. **List** open Epics, oldest first, on either forge: `python3 $t list --state open --title-prefix "Epic:"`. Keep those
   with no run label (`factory:running`, `factory:shipped`,
   `factory:over-budget`, `factory:needs-input`).
2. **Approval gate.** For each candidate, `python3 $t labels <epic>` and
   `python3 $t get <epic>`. It is drafted when it has the `factory:drafted`
   label **or** its body contains `<!-- factory:drafted` (the Epic shell's
   marker, which survives a label that never landed). It is approved when it
   is not drafted, or it has `factory:approved` or `factory:auto-approve`. A drafted Epic without one is skipped; say in the
   session `#N waits for a person's factory:approved`. Never add an approval
   label yourself (`tracker.py` refuses it). Take the oldest approved Epic;
   none → print the exit line (Output) and **stop**. Never wait, poll on a
   timer, or schedule a re-run for an Epic that doesn't exist yet.
3. **Start**, without asking: `python3 $t label <epic> --add factory:running`.
   One Epic at a time: take the next only when this one stops.
4. **Budget gate** before every round, including the first:
   `python3 $b status --epic N [--limit L]` →
   - `ok` → go on.
   - `warn` → post one warning comment (once per Epic):
     `python3 $t comment <epic> --body "Budget warning: <used>/<limit> tokens (<percent>%)"`.
   - `pause` → prepare no new unit, start no subagent;
     `python3 $t label <epic> --add factory:over-budget`, say in the session
     `Paused for the budget: <used>/<limit> tokens on #N`, and wait for the
     person (a raised `--limit`, or the label removed). Running subagents may
     finish and are recorded.
5. **Stories.** Run `/story-decomposer` on the Epic.
6. **Plan review.** Save the story bodies (`python3 $t get <story> -o <file>`)
   and follow the `plan-reviewer` skill: `python3 .agents/scripts/plan.py
   check <files>`, then `python3 .agents/scripts/plan_review.py <files>`
   (from round 2 with `--round n --prior <file>`), keyed on its exit code,
   with the reviewer model from `PLAN_REVIEW_MODEL`, never the coding model.
   `0` ready → keep its `deferred` findings for step 7. `1` needs-work → the
   blocking `findings` back to story-decomposer, at most 3 times; then the
   escalation ladder. Deferred findings never go back to story-decomposer.
   `2` or `3` → `needs-input` on the Epic: label it `factory:needs-input`,
   comment the question, and stop.
7. **Tasks.** Run `/task-decomposer` on each story whose tracks need tasks,
   or that a deferred finding names, passing that story's deferred findings
   verbatim.
8. **Waves.** Run `/wave-dispatcher --ship` on the Epic, a round at a time
   (`python3 $d prepare --max <n>`, subagents, `check`, `merge`), with step 4
   before each `prepare`. Ship upstream stories first: a dependant's PR opens
   only after theirs merge (`integrate --sync origin/main`), split per track
   when it measures over the PR budget.
9. **Record spend.** After every subagent finishes (decomposers, reviewers,
   track agents, ship-pr), record the tokens it reported:
   `python3 $b record --epic N --unit <unit> --tokens <T>` (unit: the track,
   e.g. `S1/A`, or the skill name, e.g. `story-decomposer`).
10. **Escalate** per `.agents/doctrine/escalation.md` for every loop: a unit
    in `python3 $d report` → `needs_replan` gets a diagnosis file and one rung
    with `python3 $d escalate <unit> --diagnosis <file> --outcome
    attempt|replan|needs-input [--question "..."]`. For each unit in
    `needs_input`, label its story issue (the Epic plan's `stories[].issue`):
    `python3 $t label <story> --add factory:needs-input`. Keep dispatching:
    `prepare` still starts every unit with no dependency on it.
11. **Report each round.** From `python3 $d report` and `python3 $b status`:
    print one status line in the session, and comment the round summary on
    the Epic with `python3 $t comment <epic> --body "<summary>"` (Output).
12. **Finish.** When every story is integrated and its PR merged:
    `python3 $t label <epic> --add factory:shipped --remove factory:running`,
    then go back to step 1 for the next approved Epic. If only escalated
    units, or PRs ship-pr left "ready for a person" (`merge_policy` `never`,
    or an irreversible path), remain, leave `factory:running`, say what waits
    on a person, and go back to step 1; that Epic is skipped until a person
    answers or merges.

## LLM Judgment

Use judgment only for:

- the diagnosis and the rung when a loop runs out (escalation doctrine: a
  suspected cause goes to `needs-input`, never `attempt` or `replan`);
- the question a person must answer, one sentence, on the story issue;
- reading each subagent's reported token count, the way wave-dispatcher reads
  its report.

Do not approve an Epic, overrule a reviewer's verdict, edit a subagent's code,
or start a unit while the budget says `pause`.

## Output

One status line per round in the session:

```text
factory #<epic> round <n>: done <n>/<total> · running <n> · blocked <n> · escalated <n> · budget <used>/<limit> (<percent>%, <state>)
```

The round comment on the Epic:

```markdown
**Factory round <n>** — budget <used>/<limit> tokens (<percent>%, <state>)

- Done: <units or none>
- Running: <units or none>
- Blocked: <units or none — with the note>
- Escalated: <units — rung, and the question for needs-input>
```

When nothing is left to start, print one line and exit:
`factory: done — shipped: #N, … · waiting on a person: #N (needs factory:approved), …`
(`none` where a list is empty).

## Stop Conditions

- Stop starting units at `pause`; the person decides what comes next.
- Stop the Epic when plan review exits 2 or 3, or its ladder ends with a person.
- Stop when no approved Epic is left to start (step 2); never wait for one.
- Stop when the person says stop; leave labels as they are for the next run.
- Never apply `factory:approved` or `factory:auto-approve`, never push to or
  merge into the default branch outside ship-pr's gates, never force-push.

## Token Budget

- The factory's own context: script JSON, labels and subagent reports only;
  ≤ 2,000 tokens per round of its own output.
- Round comment ≤ 150 words; status line one line. The Epic's total spend is
  bounded by `budget.py` (default 5,000,000 tokens).
