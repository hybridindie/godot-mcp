---
type: index
title: "Ship: export, tests & CI"
description: "The ship loop — export builds, run test suites headlessly, and wire the verification into CI."
created: 2026-09-19
updated: 2026-09-23
---

# Ship: export, tests & CI

The end of the loop: verification runs headless (no editor needed), so the
whole build-test-ship path works in CI.

## Export a build

```
godot_enable_toolset('export')
godot_export_list_presets()               # discover configured presets
godot_export_get_info(preset='Web')       # validate the preset's settings
godot_export_project(preset='Web', output_path='builds/web')
```

Export runs headlessly (Godot binary + export templates installed) and
reports the exit code — a non-zero exit is a finding, not a hang. Requires the
`export` toolset.

## Run the project's tests

```
godot_enable_toolset('testing')
godot_testing_run_tests(test_dir="res://tests/unit")
```

The parser understands GUT output (including GUT 9.7's quirk of omitting the
"Failing Tests" line when everything passes). A structured result carries the
pass/fail counts; `framework_absent: true` when no test framework is
installed.

GUT-specific gotchas (from the expert skill): don't `await` `node.ready` on
simple nodes, don't instantiate heavy scenes in `before_each`, reset autoload
state between tests.

## CI-shaped verification loop

The full headless loop — no live editor, no probe:

1. `godot_scripts_get_parse_errors` for every changed `.gd`
2. `godot_shader_validate` for every changed `.gdshader`
3. `godot_runtime_run_and_capture(scene=…, timeout_seconds=5)` — read
   `errors`/`warnings`; `timed_out: true` is not a crash
4. `godot_testing_run_tests(test_dir=…)` — the project's own test suite
5. `godot_export_project(preset=…, output_path=…)` — artifact with exit-code
   verdict

Each step returns structured results an agent (or a script) can gate on. The
one-call `godot_debug_workflow()` (always-on `core`) collapses steps 1–3 with
a findings/suggestions report.

## Transport notes for CI

- **stdio** (default): each CI job spawns its own server — nothing to share.
- **http**: one service can carry several concurrent jobs' verification runs,
  but the editor bridge is single-connection — for CI prefer stdio per job.
- Headless runs need a Godot binary: `GODOT_BIN` (or `godot` on PATH). The
  parse/compile checks use the same binary; version 4.4+ (4.7 validated).
- `run_and_capture` is a detached subprocess — it never blocks the bridge, so
  a long-running scene times out on its own `timeout_seconds`, not the bridge.