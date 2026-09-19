---
title: Verify your work
description: The verification stack — what each check covers, what it misses, and the recommended full pattern.
---

# Verify your work

"Verified" means different things at different layers. This page is the honest
map: what each check covers, what it **misses**, and what to compose for real
confidence.

## The stack

| Check | Tool (class) | Catches | Misses |
|-------|--------------|---------|--------|
| Parse check | `godot_scripts_get_parse_errors` (`read_only`) | GDScript **syntax** errors, with line numbers | class-API misuse (`_rng.get_noise_1d` parses clean, fails at runtime); stale cache is flagged with `rescan_pending` |
| Shader compile | `godot_shader_validate` (`read_only`) | everything the engine's compile rejects: invalid uniform hints, bad `render_mode` | runtime shader behavior (visual output) |
| Headless run | `godot_runtime_run_and_capture` (`runtime`) | runtime errors, warnings, exit codes — the **full** verification for scripts | input-dependent behavior (no play session) |
| One-call report | `godot_debug_workflow()` (`core`) | parse + tree + run + bridge in one result | same misses as its parts |
| Persistence verdicts | every mutation | what the save will keep (`persisted`/`reason`) | — |
| Play session | `godot_runtime_play_scene` + assertions | actual gameplay, input, live state | — |

## The recommended pattern

1. **Write** via `scripts_write`/`patch_script` (flushes to disk immediately).
2. **Parse**: `get_parse_errors` — fix syntax first.
3. **Compile** (shaders): `shader_validate` — the issue's exact repro
   (`uniform float edge_width : float`) parses and byte-reads clean; only the
   engine's compile catches it.
4. **Run**: `godot_runtime_run_and_capture(scene=…, timeout_seconds=5)` — read
   `errors`/`warnings`. A `timed_out: true` result is **not** a crash (games
   that never self-quit); pass `expected_timeout=true` to `godot_debug_workflow`.
5. **Play** (interactive behavior): `play_scene` + input sim + assertions.

## Why "verification" is stated this narrowly

The advertised verification used to give false confidence (#423): a VFX
subagent verified a shader via byte-equality and scripts via empty parse
errors — then 2292 runtime errors appeared at first boot. The fixes:

- `godot_shader_validate` (2026.09.19) closes the shader half.
- `get_parse_errors` documents its scope honestly; the runtime half is the
  documented `run_and_capture` pattern (which is what actually caught
  everything in the original report).

## The one-call diagnostics

```
godot_debug_workflow(scene='res://scenes/main.tscn', expected_timeout=false)
```

Returns `{bridge, scene_tree?, run?, parse{ok, errors, skipped_reason,
rescan_pending}, findings[], suggestions[]}` — findings read as ground truth:
`RUNTIME ERRORS: n`, `RUN TIMED OUT`, `NON-ZERO EXIT` (only for a real
crash), `PARSE ERRORS: n`. Pass `expected_timeout=true` for games that
legitimately run until killed.

## Honesty fields as verification

- `persisted` — will the save keep it? (act on `hint` when false)
- `undoable` — can `godot_undo` revert the batch?
- `aborted_at` / `skipped_count` — did trailing commands run?
- `rescan_pending` — was this check racing the importer scan?
- `scanning` — is the import status provisional?

## CI integration

The full verification loop runs headless (no editor): `run_and_capture` +
`run_tests` (GUT) + `export_project` are the CI-shaped tools; the live-editor
e2e suite exercises the rest on a real Godot binary.