---
name: task-decomposer
description: >
  Break a story's tracks into PR-sized, ordered tasks inside its agent-plan block — each
  naming the files, the AC it serves and an exact verify command — so a subagent can
  execute its track without asking questions. Trigger phrases: "break down this story
  into tasks", "decompose this story", "what tasks does this story need", "make this
  story executable by an agent". Use when a story has tracks and needs a step-by-step
  task list before dispatch.
---

# Task Decomposer

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 4.4.0, owner: John D
  invokes: .agents/scripts/plan.py,
           .agents/scripts/tracker.py,
           .agents/evals/story-rubric.md
  doctrine: .agents/doctrine/agent-plan-schema.md,
            .agents/doctrine/parallelization-doctrine.md,
            .agents/doctrine/ai-readable-spec-rules.md,
            .agents/doctrine/context-discovery.md
-->

Break one story's tracks into PR-sized tasks that a subagent can execute in
order without asking questions. Tasks live in the story's `agent-plan` block
(`tasks:`), not in separate issues; the dispatcher puts a track's tasks into
that track's subagent brief.

## Inputs

- Required: the story body with a valid `agent-plan` block (a file, or
  `tracker.py get <ref> -o story.md`).
- Optional: the plan review's deferred findings (`plan_review.py`'s
  `deferred` list, passed on by plan-reviewer or factory). They are task-level
  by definition: settle each one in the tasks you write, or say in the Output
  why it does not apply. Never send one back to story-decomposer.
- Read: the doctrine files above and the files each track owns.
- Do not read: unrelated modules or the whole repository.

## Deterministic Steps

1. **Gate the input.** Run `python3 .agents/scripts/plan.py check story.md`. If it fails, the story
   has no ACs, or it is larger than L, return it to `story-decomposer`.
2. **Keep the tracks.** Track ids, `owns`, `depends_on`, `consumes` and
   `verify` stay as planned. If a track must split or merge, change `tracks` first and
   re-validate; a dispatched track (`status` not `todo`) never changes.
3. **Write tasks per track,** in execution order. Each task is one PR-sized
   step (≈100 lines, ≤3 files) with:
   - `do` — verb + specific change, naming the file/function/endpoint per
     `ai-readable-spec-rules.md`, `(new)` for things that don't exist yet;
   - `files` — inside the track's `owns` (validation enforces it);
   - `depends_on` — earlier task ids it needs;
   - `verify` — the narrowest exact command that proves this task;
   - `acs` — the story ACs it serves.
   Put a test with the code it tests, in the same track. A task whose only
   test is behavioural-eval markdown (a skill or doctrine change) verifies
   with a check that fails before the work, such as `grep -q '<new rule>'
   <skill file>`; a pure-prose track declares `verify_baseline: pass`.
4. **Cover every AC.** Each story AC has at least one task; each task serves an
   AC or is a stated prerequisite of one.
5. **Check and read a brief.**
   `python3 .agents/scripts/plan.py check story.md` (add `epic.md` when you have
   it), then `python3 .agents/scripts/plan.py brief story.md --track <id>`.
   Read the brief as if you were the subagent: if it could not start without
   asking something, add that to `context` or the task. Fix the plan on `FAIL`.
6. **Quality pass.** When the caller asks for a strict review, or the tracks are
   about to be dispatched, apply the parallel-plan table of
   `.agents/evals/story-rubric.md`. It advises; it never blocks.
7. **Publish when asked.** `tracker.py put <story-ref> story.md`.

## LLM Judgment

Use judgment only for:

- task granularity and order inside a track;
- naming the concrete change and its narrowest verify command;
- what context a cold subagent is missing.

Do not invent APIs, files, commands, or acceptance criteria.

## Output

The story body with `tasks:` filled in its plan block and the generated task
checklist synced, plus one line per track: `<track> — N tasks — <verify>`.

A track with one obvious change may have a single task; an S-sized story with
one track is valid — say why parallelizing would add overhead.

## Stop Conditions

- Stop if the story plan does not validate, has no ACs, or is larger than L.
- Stop if a task needs a file outside its track's `owns`; move the file to the
  right track or report the ownership gap.
- Stop if a task cannot name a verify command.

## Token Budget

- Default: read the story, the doctrine files, and the files the tracks own.
  Read one more file when a task would otherwise invent a path or API, and say
  why.
- Target ≤ 600 words of tasks per story; do not repeat the story.
