---
name: story-decomposer
description: >
  Turn a ready Epic into story issues a subagent can pick up cold: context,
  Given/When/Then criteria, and an agent-plan block with ownership, verify commands and
  parallel tracks (a contract track first when work shares an interface), validated so
  parallel tracks never touch the same files. Trigger phrases: "decompose this epic",
  "break down this epic into stories", "create stories from this epic", "split this
  epic", "plan the parallel work for this epic". Use when the user has an Epic and wants
  stories and tracks that can be dispatched to parallel subagents.
---

# Story Decomposer

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 6.4.0, owner: John D
  invokes: .agents/skills/task-decomposer/SKILL.md,
           .agents/templates/epic/story-shell.md,
           .agents/scripts/plan.py,
           .agents/scripts/tracker.py,
           .agents/evals/story-rubric.md
  doctrine: .agents/doctrine/agent-plan-schema.md,
            .agents/doctrine/parallelization-doctrine.md,
            .agents/doctrine/ai-readable-spec-rules.md,
            .agents/doctrine/source-discipline.md
-->

Turn a ready Epic into story issues that a subagent can pick up cold. Each story
carries an `agent-plan` block with its ownership, verify command and tracks —
the units `wave-dispatcher` hands to parallel subagents. A story body is the
whole brief a subagent gets, so anything it needs to know goes in it.

## Inputs

- Required: the Epic body with a valid `agent-plan` block (a file, or
  `tracker.py get <ref> -o epic.md`).
- Read: `story-shell.md` and the doctrine files above.
- Read: the files and directories named in each story's `owns`, enough to name
  real modules, entry points and test locations.
- Do not read: unrelated code or the whole repository.

## Deterministic Steps

1. **Gate the input.** `python3 .agents/scripts/plan.py check epic.md`. If it
   fails, or the Epic has no outcome or ACs, stop and send it back to
   `epic-composer`. Note every `LEARNED <story>: ...` line it prints: those are
   confirmed causes of earlier failures in that story's paths
   (`.agents/plan-constraints.yaml`). Apply each one when you write that
   story's context and tracks — for example by keeping a model change and its
   regenerated client in the same track.
2. **Scaffold.** `python3 .agents/scripts/plan.py scaffold epic.md --out .`
   writes `story-<id>.md` for every Epic story with the plan block filled from
   the Epic — id, ACs and their wording, `depends_on` and `consumes`, `owns`,
   `verify`, a `branch`, and `must_not_touch` (everything the stories that can
   run at the same time own) — and one default track. Keep those fields; you refine, you
   do not re-slice. If a story must change shape, change the Epic plan first,
   re-check it and re-scaffold that story (`--stories S2 --force`).
3. **Write each story's prose** in its scaffolded file:
   - the user-story frame (or What/Why for spikes and technical stories);
   - **Context** a subagent with no other knowledge can act on: current
     behaviour, the files involved (named per `ai-readable-spec-rules.md`),
     what exists vs. what is new — copy it into the plan's `context`;
   - Given/When/Then criteria for each AC, and the same wording in `ac_text`.
4. **Split into tracks** only where it pays. The default single `main` track is
   right for an S-sized, single-concern story — say so. Otherwise:
   - a shared surface inside the story becomes a `kind: contract` track that
     the others depend on, each naming what it reads in `consumes`;
   - tracks that can run together own disjoint paths (tests go with the code
     they test), each with an exact `verify` and, when the story context
     mentions work it must not do, its own `context`;
   - add `integration` (`merge_order`, `verify`);
   - a track whose only tests are behavioural-eval markdown (a skill or
     doctrine change) gets a verify that fails before the work — a `grep -q`
     for the new behaviour in the file, or a lint rule — or, for pure prose,
     `verify_baseline: pass`.
   **Size the story to one PR:** estimate the integrated diff, tests
   included, against the PR budget (≤ 400 lines, ≤ 25 files). Over it, split
   the story in the Epic plan, or set `ship: per-track` so each track ships
   as its own stacked PR. Tracks that each fit can still sum past it.
5. **Check the set.** `python3 .agents/scripts/plan.py check epic.md story-*.md`
   validates every plan against the Epic, regenerates the tables, checks the
   prose and prints the track waves. Fix the plan on `FAIL`, never the checker.
6. **Read one brief as the subagent would.**
   `python3 .agents/scripts/plan.py brief story-S1.md --track main` — if it
   could not start without asking something, add that to `context`.
7. **Quality pass.** When the caller asks for a strict review, or Wave 1 is
   about to be dispatched, apply `.agents/evals/story-rubric.md` (the story
   table to each story, the parallel-plan table to the waves). It advises; it
   never blocks the output.
8. **Publish when asked.** Create each story issue with `tracker.py create`,
   write the returned numbers into the story blocks (`issue`, `branch`) and the
   Epic block (`stories[].issue`), re-sync both, and `tracker.py put` the Epic.
9. **Hand off.** Tracks that need more than one obvious change get tasks from
   `task-decomposer`; the rest are dispatchable as they are.

## LLM Judgment

Use judgment only for:

- writing context a cold subagent can act on;
- where to cut tracks and what each owns;
- whether a shared surface deserves a contract track;
- resolving ownership when the Epic leaves it ambiguous.

Do not invent requirements, file paths, commands, or dependencies. A path you
could not confirm is marked `(new)` in Context.

## Output

- One story body per Epic story, titled `Story N: <outcome>` or
  `story(scope): <outcome>`, each with the generated track table and exactly one
  `agent-plan` block.
- The track waves `plan.py check` printed, so the caller sees which tracks
  start first.
- A coverage note: every Epic AC covered by at least one story, or the gap.
- When step 7 ran, the rubric findings per story and for the waves.

## Stop Conditions

- Stop if the Epic plan does not validate; do not decompose an ambiguous outcome.
- Stop if two parallel units would own the same path and neither a contract nor
  a dependency resolves it.
- Stop if an AC cannot be made observable; return it to the acceptance linter.
- Stop if a track cannot name a verify command; ask for the repo's test command.

## Token Budget

- Default: read the Epic, the doctrine files, and the code named in `owns`. Read
  one more file only when ownership or context would otherwise be a guess, and
  say why.
- Target ≤ 400 words of prose per story; the plan block and generated tables do
  not count. Do not restate the Epic.
