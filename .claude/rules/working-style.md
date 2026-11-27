---
read_when: "Before any change: how to scope, size, and check the work"
---

# Working Style: Think First, Stay Small, Prove It

The other rules set the quality bar. This one is how you get there. For a
trivial change, use judgment.

## Before coding

- State your assumptions. If the request reads two ways, name both and ask;
  don't pick one silently. A dispatched subagent that can't ask blocks with a
  note instead.
- If a simpler approach exists, say so before building the bigger one.
- A subsystem that is planned but not built: ask before building it.

## Simplicity

- Write the minimum code that meets the acceptance criteria. No features,
  options or config nobody asked for.
- No abstraction with a single caller. No handling for states that can't
  occur; boundary errors still follow `error-handling.md`.
- If it could be a quarter of the size, rewrite it before review.

## Surgical diffs

- Every changed line traces to the issue. Stay inside the files you own;
  anything else becomes a note or a new issue.
- Match the surrounding style. Don't reformat, rename or "improve" adjacent
  code.
- Remove what your change left unused. Report dead code that was already there;
  don't delete it.

## Verify

- Turn the task into a check: a bug gets a failing reproduction test, a feature
  gets a failing test for its acceptance criterion, and a refactor stays green
  before and after (`testing.md`).
- For multi-step work, state the plan as `step → verify: <command>`.

## Answers

- Implementation: code first, minimal prose. Process: bullets.
- Comments explain *why*, not *what*.
