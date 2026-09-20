---
name: godot-playtest-and-debug
description: Run, inspect, and debug a live Godot game through the godot-mcp server — play a scene in the editor, read the running scene tree, sample properties, simulate input, assert state, and diagnose errors. Use when the user wants to play-test, reproduce a bug, or debug runtime behavior in Godot via godot-mcp. Triggers on "play-test in Godot", "run the game and check", "simulate input in Godot", "why does my Godot game crash", "debug the running scene", "inspect the live game".
---

# godot: play-test and debug

Drive a live game session and diagnose failures. Godot must be open with the addon enabled (see `godot-getting-started`). The server's `/mcp__godot-mcp__play_test`, `/mcp__godot-mcp__debug_scene`, and `/mcp__godot-mcp__troubleshoot` prompts cover the parameterized flows.

**Two run modes — pick the right one:**

- **Headless smoke test** (`runtime` toolset): `godot_runtime_run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)` runs the project headless (no editor play session, no probe needed) and returns `errors`/`warnings`/`output` + exit code. Use it to answer "does it run at all". For the full one-call report (parse + tree + run + bridge), `godot_debug_workflow(scene='res://scenes/main.tscn', expected_timeout=<true if the game never quits>)` is in `core` — no extra toolset needed.
- **Live play session** (`runtime` + `input` + `testing` + `debugger` toolsets): everything below — interactive inspection, input simulation, assertions, breakpoints. This needs the runtime probe.

## 1. Enable the toolsets

```
godot_enable_toolset('runtime')         # play/stop/is_playing, run_and_capture
godot_enable_toolset('input')           # key/mouse/action input, sequences, recording
godot_enable_toolset('testing')         # assertions, scenarios, screenshots, stress
godot_enable_toolset('debugger')        # breakpoints, stepping, expressions
godot_enable_toolset('resources_edit')  # to register the runtime probe if needed
godot_enable_toolset('profiling')       # optional: FPS/draw calls/memory while running
```

**Efficiency note:** enable only the toolsets the current task needs — `runtime` alone answers "does it run"; add `input`/`testing`/`debugger` only when driving the game live.

## 2. Make sure the runtime probe is registered

Live inspection and input need the `MCPRuntimeProbe` autoload **in the consuming game's project** (it runs in the game, not the editor, and no-ops in exported builds).

```
godot_inspection_get_project_info()        # check autoloads for 'MCPRuntimeProbe'
godot_resources_edit_register_autoload(
    name='MCPRuntimeProbe',
    path='res://addons/godot_mcp/mcp_runtime_probe.gd')   # only if missing
```

## 3. Play and inspect

```
godot_runtime_play_scene(scene_path='res://scenes/main.tscn')
godot_runtime_is_playing()                 # → {'playing': true}
godot_runtime_get_game_scene_tree()        # the LIVE hierarchy (not the editor tree)
godot_runtime_get_game_output()            # the game's print/error/warning stream (#534)
godot_runtime_monitor_property(node_path='/root/Main/Player', property='position', samples=30)
godot_runtime_get_property_samples()       # [{frame, value}] once the capture completes
godot_runtime_find_ui_elements(text='Start')  # locate a Control by its text
```

`godot_runtime_get_game_output()` reads the running game's console — print lines, script
errors (with stack-trace rationale), warnings — from a bounded ring with a `since_seq`
cursor. Works while the game is paused at a debugger break: that's when crash traces are
readable. Pass the previous call's `next_seq` as `since_seq` for incremental pulls.

## 4. Simulate input

```
godot_input_simulate_action(action='ui_right', pressed=true)   # hold
godot_input_simulate_action(action='ui_right', pressed=false)  # release
godot_input_simulate_key(key='Space', pressed=true)
godot_input_simulate_mouse(x=200, y=150, button='left')        # move / click
godot_input_play_sequence(events=[...], delay_ms=100)          # replay a recorded macro
godot_input_record()                       # start capturing (include_motion=false)
godot_input_stop_recording()               # → captured events: feed them to play_sequence
godot_input_get_stats()                    # how many events the game acknowledged
```

## 5. Assert, measure, then stop

```
godot_testing_assert_node_state(node_path='/root/Main/Player', property='visible', expected=true)   # op='==' default; also '>=','<=' etc.
godot_testing_run_test_scenario(scene_path='res://scenes/main.tscn', events=[...],
                                 assertions=[{'node_path': '...', 'property': '...', 'expected': ...}])
godot_testing_run_stress_test()                        # fuzz with random input
godot_testing_compare_screenshots(image_a='<base64>', image_b='<base64>', tolerance=0.0)
godot_profiling_get_performance_monitors(scope='game')  # FPS, draw calls, memory
godot_runtime_stop_scene()
```

`godot_editor_capture_screenshot()` (the `editor` toolset) provides base64 PNGs for the diff tool.

## Debugging failures

- **Crash on play** → `godot_runtime_run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)`, then read `errors`/`warnings` (null refs, missing nodes, bad signal connections). A `timed_out: true` result is **not** a crash — games that never self-quit always time out; pass `expected_timeout=true` on `godot_debug_workflow` or treat the timeout as success when the game has no quit path.
- **Script won't parse** → `godot_scripts_get_parse_errors(script_path='res://scripts/x.gd')`, fix the reported line/column. If the errors follow a *fresh* `class_name` write and carry `rescan_pending: true`, the editor's rescan hadn't flushed — re-check before "fixing" code that is already correct.
- **Input does nothing** → confirm `godot_runtime_is_playing()` is true and the probe autoload is present (step 2); check a full-screen overlay isn't eating input (`mouse_filter`). If input tools return `PRECONDITION_FAILED` with `required=game_not_breaked`, the game is frozen at a debugger break — `godot_debugger_continue_execution()` before injecting input.
- **Break and step through code** → pause on the spot with `godot_debugger_force_break()`, or pre-arm `godot_debugger_set_breakpoint(path='res://scripts/player.gd', line=42)`. Then read `godot_debugger_get_stack_frames()`, `godot_debugger_get_frame_variables()`, `godot_debugger_evaluate_expression(expression='player.health')`, and step with `godot_debugger_step_into()` / `godot_debugger_step_over()` / `godot_debugger_step_out()`. Resume with `godot_debugger_continue_execution()`. Clean up with `godot_debugger_remove_breakpoint(path=..., line=...)` or `godot_debugger_clear_breakpoints()`.
  - Note: `force_break` only lands if the game's main loop calls `check_force_break()` (the probe sets `force_break_pending`); breakpoints trigger on their own line.
  - While breaked, `godot_input_get_stats().injected` does not move — refused input is not queued. That's the signal, not a bug.
- Stuck? Run `godot_get_server_info()` and follow `next_steps`, or use the `troubleshoot` prompt.