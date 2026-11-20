---
type: index
title: "Ship: export, tests & CI"
description: "The ship loop — export builds, run test suites headlessly, and wire the verification into CI."
created: 2026-09-19
updated: 2026-10-12
---

# Ship: export, tests & CI

The end of the loop: verification runs headless (no editor needed), so the whole
build-test-ship path works in CI. You ask in plain language; the assistant does the rest.

## Export a build

You: *"Export a Web build."*

The assistant lists your project's export presets, checks the one you want, and runs it.
Export is headless (Godot binary + export templates installed) and reports the exit code — a
non-zero exit is a finding, not a hang. Requires the `export` toolset.

```jsonc
godot_enable_toolset(category="export")
godot_export_list_presets()
// { "presets": [{ "name": "Web", "platform": "Web", ... }] }

godot_export_project(preset="Web", output_path="builds/web/index.html", confirm=true)
// { "preset": "Web", "output_path": "builds/web/index.html", "exported": true, "exit_code": 0, ... }
```

## Run the project's tests

You: *"Run the project's unit tests."*

The assistant runs the suite and parses the output — it understands GUT, including GUT 9.7's
quirk of omitting the "Failing Tests" line when everything passes — and reports the pass/fail
counts (or `framework_absent: true` when no test framework is installed).

```jsonc
godot_enable_toolset(category="testing")
godot_testing_run_tests(test_dir="res://tests/unit")
// { "framework_absent": false, "passed": 60, "failed": 0, ... }
```

GUT-specific gotchas (from the expert skill): don't `await` `node.ready` on simple nodes,
don't instantiate heavy scenes in `before_each`, reset autoload state between tests.

## CI-shaped verification loop

::: info Under the hood
Every step returns structured results an agent or a script can gate on — no human reading
logs. The one-call debug workflow collapses the first three.
:::

The full headless loop — no live editor, no probe:

1. **Parse** every changed `.gd` for syntax errors.
2. **Compile-check** every changed `.gdshader`.
3. **Run** the scene headlessly and read its errors and warnings — a timeout is not a crash.
4. **Test** — run the project's own suite.
5. **Export** — produce the build artifact, with an exit-code verdict.

Each step returns structured results an agent (or a script) can gate on; ask the assistant to
"run the debug workflow" to collapse the first three into one findings report.

```jsonc
godot_debug_workflow(scene="res://scenes/main.tscn", expected_timeout=true)
// { "findings": ["PARSE ERRORS: 0", "RUNTIME ERRORS: 0", "RUN TIMED OUT"], ... }

godot_enable_toolset(category="analysis")
godot_analysis_validate_project(paths=["res://scripts", "res://scenes"], include_warnings=true)
// { "valid": true, "findings": [] }
```

## Transport notes for CI

- **stdio** (default): each CI job spawns its own server — nothing to share.
- **http**: one service can carry several concurrent jobs' verification runs, but the editor
  bridge is single-connection — for CI prefer stdio per job.
- Headless runs need a Godot binary: `GODOT_BIN` (or `godot` on PATH). The parse/compile checks
  use the same binary; version 4.4+ (4.7 validated).
- A headless run is a detached subprocess — it never blocks the bridge, so a long-running scene
  times out on its own timer, not the bridge's.
