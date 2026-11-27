<!--
  parallelization-doctrine.md — Shared parallel-first doctrine
  Referenced by: epic-composer, story-decomposer, task-decomposer, wave-dispatcher
  version: 2.1.0, owner: John D
  Single source of truth for the contract → tracks → integration pattern and the
  metadata that makes work dispatchable to subagents and teams.
-->

# Parallel-First Doctrine

Default to parallel. Sequence work only when one unit genuinely needs another
unit's output, and name that dependency. The goal is not “more agents”; it is
that a lead can dispatch a wave and know it will not collide.

## Metadata every unit carries

| Field | Meaning |
|---|---|
| `depends_on` | Units that must land first (a real output dependency) |
| `parallel_with` | Units that can run at the same time |
| `owns` | Files/directories this unit may change |
| `must_not_touch` | Paths owned by a parallel unit |
| `contract` | Interface/type/schema/file format the tracks share |
| `verify` | Command or check that proves the unit is done |
| `integration` | Merge order and the end-to-end check after the tracks |

Two units may run in parallel only when their `owns` sets are disjoint and
neither needs the other's output.

These fields live in each issue's `agent-plan` block
(`.agents/doctrine/agent-plan-schema.md`); `plan.py validate` enforces the rule
above, and waves are computed from `depends_on` rather than written down.

## The pattern

1. **Shared contract** — define the interface, type, schema, or file format
   both sides need. One unit owns it; it lands first.
2. **Tracks** — independent streams of work behind the contract. Each names
   its owned paths and its verify command.
3. **Integration** — merge the tracks in a stated order and run the end-to-end
   check. This unit owns conflicts and the final proof.

```
Shared contract (sequential)
  → Track A (parallel, after contract)   owns src/api/**
  → Track B (parallel, after contract)   owns src/ui/**
Integration (sequential)                verifies end-to-end
```

## Dispatch

A track is dispatchable when a subagent or team can start from the story alone:

- the contract is linked and stable;
- the owned paths are listed, and the paths it must not touch are listed;
- the verify command is exact;
- the integration order is known.

Give each subagent one track. Do not let two tracks edit the same file; if they
must, stop and either split the file's scope or sequence the tracks.

`wave-dispatcher` does this mechanically: one worktree and one subagent per
runnable track, a scope check on the diff, the track's verify, then a merge
into the story branch in `integration.merge_order`.

## When not to parallelize

- The unit is S-sized and one coherent change.
- The work touches a single file with tightly coupled edits.
- A track would spend more time reading the contract than doing the work.
- The dependency is genuinely sequential (a migration before a backfill).

Saying “sequential because …” is a good answer. Pretending two tracks are
independent when they share files is the failure mode.

## Anti-patterns

- Contract defined *after* the tracks start.
- Parallel tracks with overlapping ownership.
- “Parallel” tasks with no verify step.
- Integration left implicit (“merge the branches”).
- More tracks than there are independent concerns.
