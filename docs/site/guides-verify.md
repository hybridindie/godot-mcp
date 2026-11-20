---
type: index
title: "Verify your work"
description: "The verification stack — what each check covers, what it misses, and the recommended full pattern."
created: 2026-09-19
updated: 2026-10-12
---

# Verify your work

Ask the assistant to *prove* an action landed, not just perform it. "Verified" means
different things at different layers — this page is the honest map: what each check covers,
what it **misses**, and what to compose for real confidence.

## The stack

| Check | Tool (class) | Catches | Misses |
|-------|--------------|---------|--------|
| Parse check | `godot_scripts_get_parse_errors` (`read_only`) | GDScript **syntax** errors, with line numbers | class-API misuse (`_rng.get_noise_1d` parses clean, fails at runtime); a stale cache is flagged with `rescan_pending` |
| Shader compile | `godot_shader_validate` (`read_only`) | everything the engine's compile rejects: invalid uniform hints, bad `render_mode` | runtime shader behavior (the visual output) |
| Headless run | `godot_runtime_run_and_capture` (`runtime`) | runtime errors, warnings, exit codes — the **full** verification for scripts | input-dependent behavior (no play session) |
| One-call report | `godot_debug_workflow` (`core`) | parse + tree + run + bridge in one result | the same misses as its parts |
| Persistence verdicts | every mutation | what the save will keep (`persisted`/`reason`) | — |
| Play session | `godot_runtime_play_scene` + assertions | actual gameplay, input, live state | — |

## The recommended pattern

1. **Write** via `scripts_write`/`patch_script` — it flushes to disk immediately.
2. **Parse** — fix syntax errors first.
3. **Compile-check** shaders — e.g. `uniform float edge_width : float` parses and byte-reads
   clean; only the engine's compile catches it.
4. **Run** the scene headlessly and read the errors/warnings. A `timed_out: true` is **not** a
   crash (games that never self-quit).
5. **Play** for interactive behavior — input simulation plus assertions.

```jsonc
godot_scripts_write(script_path="res://scripts/player.gd", content="extends CharacterBody2D\n...")
godot_scripts_get_parse_errors(script_path="res://scripts/player.gd")
// { "errors": [], "rescan_pending": false }

godot_shader_validate(shader_path="res://shaders/flash.gdshader")
// { "ok": true, "errors": [] }

godot_runtime_run_and_capture(scene="res://scenes/main.tscn", timeout_seconds=5)
// { "exit_code": 0, "timed_out": false, "errors": [], "warnings": [] }

godot_runtime_play_scene(scene_path="res://scenes/main.tscn")
godot_testing_assert_node_state(node_path="/root/Main/Player", property="visible", expected=true)
```

## Why "verification" is stated this narrowly

The advertised verification used to give false confidence (#423): a VFX subagent verified a
shader via byte-equality and scripts via empty parse errors — then 2292 runtime errors
appeared at first boot. The fix: the shader check closes the shader half, and the parse check
documents its scope honestly — the runtime half is what actually caught everything.

## The one-call diagnostics

You: *"Run the full diagnostics on the main scene."*

::: info Under the hood
The assistant runs one call that returns parse + tree + run + bridge together, plus a
`findings` list that reads as ground truth — `RUNTIME ERRORS: n`, `RUN TIMED OUT`, `NON-ZERO
EXIT` (only for a real crash), `PARSE ERRORS: n`. For a game that legitimately runs until
killed, tell the assistant the timeout is expected.
:::

## Honesty fields as verification

- `persisted` — will the save keep it? (act on the hint when false)
- `undoable` — can the batch be undone?
- `aborted_at` / `skipped_count` — did the trailing commands run?
- `rescan_pending` — was this check racing the importer scan?
- `scanning` — is the import status provisional?

## CI integration

The full verification loop runs headless (no editor): run + test + export are the CI-shaped
steps; the live-editor e2e suite exercises the rest on a real Godot binary. The addon's own
logic is pinned the same way — headless `SceneTree` exercisers under `godot/tests/` run via
pytest whenever a Godot binary is present (issue #524).
