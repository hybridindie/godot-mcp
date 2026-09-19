---
type: index
title: "Play-test & debug"
description: "The live loop — play, inspect, simulate input, assert, break and step through the debugger."
created: 2026-09-19
updated: 2026-09-19
---

# Play-test & debug

The live loop against a real running game. Requires the `runtime`, `input`,
`testing`, and `debugger` toolsets plus the `MCPRuntimeProbe` autoload in the
game's project.

## Two run modes — pick the right one

| Mode | Toolset | Answers |
|------|---------|---------|
| Headless smoke test | `runtime` | "does it run at all" — no editor play session, no probe |
| Live play session | `runtime` + `input` + `testing` + `debugger` | interactive inspection, input, assertions, breakpoints |

For the full one-call report: `godot_debug_workflow(scene=…, expected_timeout=…)`
(always-on `core` — no extra toolset needed).

## 1. Register the runtime probe

```
godot_inspection_get_project_info()      # check autoloads for MCPRuntimeProbe
godot_resources_edit_register_autoload(name='MCPRuntimeProbe',
    path='res://addons/godot_mcp/mcp_runtime_probe.gd')   # only if missing
```

The probe runs in the game (not the editor) and no-ops in exported builds.

## 2. Play and inspect

```
godot_runtime_play_scene(scene_path='res://scenes/main.tscn')
godot_runtime_is_playing()                  # → {playing: true, paused: …}
godot_runtime_get_game_scene_tree()         # the LIVE hierarchy, not the editor tree
godot_runtime_monitor_property(node_path='/root/Main/Player', property='position', samples=30)
godot_runtime_get_property_samples()        # [{frame, value}]
godot_runtime_find_ui_elements(text='Start')  # locate a Control by its text
godot_profiling_get_performance_monitors(scope='game')  # FPS / draw calls / memory
```

Pending results carry a `reason` token (`capture_pending`, `probe_pending`) —
the tool relays it in the timeout error; keep polling rather than re-issuing.

## 3. Simulate input

```
godot_input_simulate_action(action='ui_right', pressed=true)   # hold
godot_input_simulate_action(action='ui_right', pressed=false)  # release
godot_input_simulate_key(key='Space', pressed=true)
godot_input_simulate_mouse(x=200, y=150, button='left')
godot_input_play_sequence(events=[...], delay_ms=100)          # replay a recording
godot_input_record() / godot_input_stop_recording()            # capture a macro
godot_input_get_stats()                                        # events the game acknowledged
```

While the game is paused at a debugger break, input is **refused**
(`PRECONDITION_FAILED [required=game_not_breaked]`) — continue execution
first. Frozen `input_get_stats().injected` is the signal, not a bug.

## 4. Assert state

```
godot_testing_assert_node_state(node_path='/root/Main/Player',
                                property='visible', expected=true)
godot_testing_run_test_scenario(scene_path='res://scenes/main.tscn',
                                events=[...], assertions=[...])
godot_testing_run_stress_test()          # fuzz with random input
godot_testing_compare_screenshots(image_a=…, image_b=…, tolerance=0.0)
```

## 5. Break and step

```
godot_debugger_set_breakpoint(path='res://scripts/player.gd', line=42)
godot_debugger_force_break()               # pause on the spot (probe services it)
godot_debugger_get_stack_frames()
godot_debugger_get_frame_variables()
godot_debugger_evaluate_expression(expression='player.health')
godot_debugger_step_over() / step_into() / step_out()
godot_debugger_continue_execution()
```

Note: `force_break` only lands if the game's main loop calls
`check_force_break()` (the probe sets `force_break_pending`); breakpoints
trigger on their own line.

## Debugging failures

| Symptom | First move |
|---------|-----------|
| Crash on play | `godot_runtime_run_and_capture` → read `errors`/`warnings` |
| `timed_out: true` | not a crash — games that never self-quit always time out; `expected_timeout=true` on `godot_debug_workflow` |
| Script "won't parse" | `godot_scripts_get_parse_errors`; if `rescan_pending: true`, re-check before "fixing" |
| Input does nothing | `is_playing` true? probe registered? full-screen overlay eating input (`mouse_filter`)? break gate? |
| Stuck | `godot_get_server_info()` → `next_steps`, or the `troubleshoot` prompt |

Always `godot_runtime_stop_scene()` when done.