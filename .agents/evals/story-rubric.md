<!--
  story-rubric.md — optional story/task quality pass
  Referenced by: story-decomposer, task-decomposer (quality-pass step, optional)
  version: 3.0.2, owner: John D
  Advice, not a gate. Use it before dispatching a wave or when the user asks
  for a strict review.
-->

# Story Quality Pass (optional)

## The story

| Question | Signal |
|---|---|
| Is it a vertical slice that can ship alone? | no horizontal layer |
| Does it have checkable acceptance criteria? | each one can fail |
| Is it S/M/L, with L at most ~3 days? | split anything larger |
| Does it name the files/modules it will change? | no pronouns, no “the backend” |
| Does it link the Epic and the ACs it covers? | traceable both ways |
| Does it state a real risk, flag, or rollback where relevant? | not “N/A” by default |

## The parallel plan

| Question | Signal |
|---|---|
| Is there a shared contract, owned by one unit? | tracks are not guessing |
| Do parallel stories have disjoint `owns`? | no file collisions |
| Is `depends_on` a real output dependency? | not “safer this way” |
| Is the integration unit explicit, with a verify command? | merge order is known |
| Could Wave 1 be dispatched today? | no hidden context |

## The task checklist

| Question | Signal |
|---|---|
| Is each task PR-sized and named by file? | ~100 lines, ≤3 files |
| Does each task have a verify step? | observable done |
| Are tests interleaved, not a final task? | tests next to the code |
| Is each task traced to an AC or labelled prerequisite? | no orphan work |
| Does the integration task prove the story's ACs? | end-to-end check |

## Report

List only the gaps that change the plan, with the smallest fix. An optional
verdict — **Ready to dispatch** / **Needs work** / **Blocked** — plus the top
three fixes is enough.
