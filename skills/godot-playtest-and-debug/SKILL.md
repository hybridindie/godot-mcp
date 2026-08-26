---
name: godot-playtest-and-debug
description: Run, inspect, and debug a live Godot game through the godot-mcp server — play a scene in the editor, read the running scene tree, sample properties, simulate input, assert state, and diagnose errors. Use when the user wants to play-test, reproduce a bug, or debug runtime behavior in Godot via godot-mcp. Triggers on "play-test in Godot", "run the game and check", "simulate input in Godot", "why does my Godot game crash", "debug the running scene", "inspect the live game".
---

# godot: play-test and debug

Drive a live game session with the `runtime`, `input`, and `testing` toolsets, and diagnose failures. Godot must be open with the addon enabled (see `godot-getting-started`). The server's `/mcp__godot-mcp__play_test`, `/mcp__godot-mcp__debug_scene`, and `/mcp__godot-mcp__troubleshoot` prompts cover the parameterized flows.

## 1. Enable the toolsets

```
godot_enable_toolset('runtime')
godot_enable_toolset('input')
godot_enable_toolset('testing')
godot_enable_toolset('resources_edit')   # to register the runtime probe if needed
```

## 2. Make sure the runtime probe is registered

Live inspection/input needs the `MCPRuntimeProbe` autoload.

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
godot_runtime_get_game_scene_tree()        # the live hierarchy
godot_runtime_monitor_property(node_path='/root/Main/Player', property='position', samples=30)
godot_runtime_get_property_samples()        # collect the sampled values
```

## 4. Simulate input

```
godot_input_simulate_action(action='ui_right', pressed=true)   # hold
godot_input_simulate_action(action='ui_right', pressed=false)  # release
godot_input_simulate_key(key='Space', pressed=true)
godot_input_play_sequence(events=[...], delay_ms=100)          # replay a macro
```

## 5. Assert state, then stop

```
godot_testing_assert_node_state(node_path='/root/Main/Player', property='visible', expected=true)
godot_runtime_stop_scene()
```

## Debugging failures

- **Crash on play** → `godot_runtime_run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)`, then read `errors`/`warnings` (null refs, missing nodes, bad signal connections).
- **Script won't parse** → `godot_scripts_get_parse_errors(script_path='res://scripts/x.gd')`, fix the reported line/column.
- **Input does nothing** → confirm `godot_runtime_is_playing()` is true and the probe autoload is present (step 2).
- **Step through code** → enable `debugger` + `runtime`, set a breakpoint, inspect the stack.
- Stuck? Run `godot_get_server_info()` and follow `next_steps`, or use the `troubleshoot` prompt.
