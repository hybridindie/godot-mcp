<!--
  escalation.md — what a loop does after it keeps failing
  Referenced by: wave-dispatcher (dispatch.py escalate), agent-plan-schema
  version: 1.0.0, owner: John D
  One ladder for every loop: three failures, then a diagnosis, then exactly
  one rung — one informed attempt, one replan, or a person.
-->

# The escalation ladder

Any loop that retries work — a track's check, a CI run, a review round — climbs
the same ladder. Retrying the same thing a fourth time with the same
information is not a rung.

1. **Three failures.** A unit gets 3 attempts. Each failed check goes back
   through `dispatch.py retry` with its findings; after the third, `retry`
   blocks the unit for replanning and `report` lists it under `needs_replan`.
2. **Diagnose.** Before anything else runs, write a diagnosis (below). It is
   posted on the story issue, so the reason for the next step is on record.
3. **Take one rung**, with `dispatch.py escalate <unit> --diagnosis <file>
   --outcome <rung>`:

   | Outcome | When | What happens | Limit |
   |---|---|---|---|
   | `attempt` | the cause is confirmed and the fix lies inside the track's `owns` | the worktree is reset to the story branch and an attempt-4 brief carries the diagnosis | once per unit; a fifth attempt is refused |
   | `replan` | the cause is confirmed and lies in the plan: wrong ownership, a missing edge, a bad contract, a verify that cannot pass | the unit stays blocked with the diagnosis as its note and stays in `needs_replan` | once per unit; afterwards only `needs-input` |
   | `needs-input` | the cause is not confirmed, or only a person can decide it (a product choice, credentials, an external system) | the unit is blocked with `--question` as its note and `report` lists it under `needs_input` | always available; `--question` is required |

   Refused calls exit with code 2. When the one `attempt` or the one `replan`
   also fails, the next rung is `needs-input`: the ladder ends with a person,
   never with another loop.

Escalating a unit blocks only that unit and the units that depend on it.
Everything else in the wave keeps running: `prepare` still starts any unit with
no `depends_on` path to it.

## What a diagnosis contains

A diagnosis is a short Markdown file. It must have:

- **Symptom** — what failed, quoted: the failing check, the last verify output
  tail, the findings from each of the 3 attempts.
- **What changed between attempts** — and why each fix did not hold. Three
  attempts that hit the same wall are one data point, not three.
- **Cause** — one sentence, marked *confirmed* or *suspected* (see below).
- **Evidence** — the command, file and line, or log excerpt that shows it.
- **Rung and why** — which outcome follows from the cause, and for
  `attempt`, the exact change the fourth attempt makes.
- **Lesson** (optional) — a constraint later plans should follow, with the
  paths it applies to. Pass it as `--lesson` and `--lesson-paths`.

## When a cause counts as confirmed

A cause is **confirmed** only when at least one of these holds:

- **Reproduced:** a command fails for that reason on its own, outside the
  attempt that hit it (a minimal test, a single verify run, a diff against the
  story branch).
- **Predicted:** changing only that thing makes the failure go away or change
  in the way the cause predicts.
- **Read from the source:** the code, plan or tool output states it directly —
  an ownership rule in `plan.py validate`, an error message naming the file, a
  contract that does not export the symbol a track consumes.

A plausible story that fits the symptoms is *suspected*, not confirmed. A
suspected cause may not take `attempt` or `replan`, and may not be recorded as a
lesson: it goes to `needs-input`, with the suspicion stated in the question.

## Lessons

A confirmed cause that would trip later plans too is recorded with
`--lesson`/`--lesson-paths` on the same `escalate` call. It is written to
`.agents/plan-constraints.yaml` with the unit as `source` and today's date,
de-duplicated like `dispatch.py learn`, and lands through the reviewed PR that
carries the run — see "Lessons from earlier runs" in
[`agent-plan-schema.md`](agent-plan-schema.md).
