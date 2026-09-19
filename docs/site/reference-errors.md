---
type: index
title: "Errors & recovery"
description: "The stable error-code enum and the recovery table — every failure names its fix."
created: 2026-09-19
updated: 2026-09-19
---

# Errors & recovery

Errors are structured data an agent can act on. Never a stack trace, never
silent, and every failure names a fix.

## The error-code enum

| Code | Meaning | Typical cause |
|------|---------|---------------|
| `PRECONDITION_FAILED` | a required state is missing | no scene open, missing `confirm`, toolset version gate |
| `RESOURCE_NOT_FOUND` | a node/scene/script/resource path does not exist | typo'd path; use `get_scene_tree` / `get_filesystem_tree` first |
| `VALIDATION_ERROR` | parameters are malformed or refused | unknown ProjectSettings key, dimension mismatch, bad enum value |
| `BRIDGE_DISCONNECTED` | Godot is not reachable | editor closed / addon disabled / bridge URL wrong |
| `TIMEOUT` | the request outlived its timeout (may carry a readiness `reason`) | a capture that never landed; a stalled editor |
| `INTERNAL_ERROR` | a handler failed without producing a response | a GDScript error inside the addon (see the editor's Output panel) |
| `APPROVAL_DENIED` | the human declined an approval | n/a — retry with different intent |

## The recovery table

| Error / symptom | Fix |
|-----------------|-----|
| `unknown tool` | the toolset isn't enabled → `godot_enable_toolset(...)`; or you mixed a server-side tool with an editor tool |
| `[required=active_scene]` | `godot_scene_edit_open_scene(path)` or `create_scene` |
| `[required=confirm]` | destructive call → `dry_run` first, then `confirm=True` |
| `[required=bridge_connected]` | open Godot with the addon; check the status dock |
| `[required=runtime_probe]` | register `MCPRuntimeProbe` as an autoload |
| `[required=game_not_breaked]` | the game is frozen at a debugger break → `godot_debugger_continue_execution` |
| `[required=godot_version]` | the toolset needs Godot 4.4+ → upgrade the editor |
| `VALIDATION_ERROR: Unknown ProjectSettings key … did you mean …` | use the suggested key (e.g. `application/run/main_scene`, not `application/config/main_scene`) |
| `persisted: false` + `hint` | act on the hint (e.g. `godot_scene_edit_set_editable_children`) or retarget |
| `rescan_pending: true` | re-run the parse check once; the editor's scan hadn't flushed |
| `NON-ZERO EXIT` on a real crash | read `errors[]` from the run; fix and re-verify |
| `RUN TIMED OUT` | if the game never self-quits, pass `expected_timeout=true` to `godot_debug_workflow` |

## Design rules

1. **Failures are data.** `{ok: false, error, hint}` crosses the envelope;
   the server shapes the same structure into a `ToolError` for the client.
2. **`hint` is for recovery** — written for an agent with no human in the
   loop. A hint that restates the code is a bug.
3. **Preconditions carry `required`** — the machine-checkable name of what to
   satisfy.
4. **No partial success.** A result never reads as success when the effect
   half-failed: `aborted_at`, `undoable`, `persisted`, and `rescan_pending`
   exist so the agent never has to guess.
5. **No invented codes.** Clients match on the enum; a new code is an additive
   contract change.

The envelope-level rules are pinned by contract tests against a fake addon
peer — a shape change without a contract-test update is a drift bug.