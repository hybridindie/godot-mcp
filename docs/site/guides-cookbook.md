---
type: index
title: "Cookbook: what to ask, and what the agent does"
description: "Prompt-first recipes for the whole loop — inspect, build, script, physics, save, preview, run, play-test, debug, batch, authoring, validate, and recover — with the MCP calls the agent makes under the hood."
created: 2026-11-05
updated: 2026-11-20
---

# Cookbook: what to ask, and what the agent does

Every recipe starts with **what you say** and what the assistant does in the
editor. Say it the way you'd say it to a person — "add a player I can move" is
enough. If you know the exact Godot type or property, say that too; the
assistant uses the same tools either way. The concrete MCP calls are under
**Under the hood**, there for transparency and for agents that need the exact
shape.

::: tip Two registers, one surface
You don't have to learn Godot vocabulary to get useful work done. But if you do
know it, you can be precise — the recipes below show both a plain-language
prompt and, where it helps, an "or say it precisely" version. The deeper
debugging, batch, authoring, and validation recipes are written for that second
register.
:::

For one continuous build instead of short recipes, use the
[Full walkthrough](guides-walkthrough.md).

::: info Gating
Only `core` + `inspection` are on by default. The assistant enables the toolset
it needs (`godot_enable_toolset(category="scene_edit")`) before using it; you
never manage gates. The enable result includes the newly enabled tools and their
input schemas.
:::

## 1. Check the connection and see what's available

**You say**

> "Is my Godot editor hooked up? I want to start building."

**What happens**

- The assistant checks the bridge and reports the server version.
- It lists the toolsets and which are already enabled.
- It enables `scene_edit` and confirms the new tools are callable.
- If the bridge is down, its report names the fix (open Godot with the addon on, check the dock).

**Under the hood**

```jsonc
godot_health_check()
// { "bridge_connected": true, "version": "2026.11.04b2", "bridge_url": "ws://127.0.0.1:9080", ... }

godot_get_server_info()
// { "version": "...", "contract_version": 1, "toolsets": [...], "active_scene": {...}, "next_steps": [...] }

godot_list_toolsets()
// { "toolsets": [{ "name": "scene_edit", "enabled": false, "min_godot": "4.4", ... }] }

godot_enable_toolset(category="scene_edit")
// { "name": "scene_edit", "enabled": true, "tools": [{ "name": "godot_scene_edit_create_node", "input_schema": {...} }] }
```

## 2. Ask it to read the scene before changing it

**You say**

> "What am I looking at? Give me the lay of the land before you change anything."

**What happens**

- The assistant names the open scene and whether it has unsaved edits.
- It lists the scene tree down a couple of levels.
- It reads the Player's script properties and its position.
- It reports scene-relative paths (`.` for the root, `Player/Weapon` below it) that it can pass straight back to the edit tools.

**Under the hood**

```jsonc
godot_inspection_get_project_info()
// { "name": "MyGame", "godot_version": "4.8.beta2", "main_scene": "res://scenes/main.tscn", "autoloads": [...], "input_actions": [...] }

godot_inspection_get_active_scene()
// { "is_open": true, "path": "res://scenes/main.tscn", "name": "main", "dirty": false }

godot_inspection_get_scene_tree(max_depth=2)
// { "tree": { "name": "Main", "type": "Node2D", "path": ".", "children": [...] } }

godot_inspection_get_node_properties(node_path="Player")
// { "node_path": "Player", "type": "CharacterBody2D", "script": "res://scripts/player.gd", "properties": {...}, "children": [...] }

godot_inspection_get_node_property(node_path="Player", property="position")
// { "node_path": "Player", "property": "position", "value": { "x": 400, "y": 300 }, "exists": true }
```

## 3. Add a player character

**You say**

> "Add a player character I can move around."

**Or say it precisely**

> "Add a CharacterBody2D named Player at (400, 300), with a CollisionShape2D and a Camera2D as children."

**What happens**

- The assistant creates the body, sets its position, adds the two children, and (if you ask) saves the scene.
- It reports the new node path and whether a save will keep it.
- One create operation, one undo step.

**Under the hood**

```jsonc
godot_composite_compose_node(
  parent_path=".", node_type="CharacterBody2D", node_name="Player",
  properties={"position": {"x": 400, "y": 300}},
  children=[
    {"node_type": "CollisionShape2D", "node_name": "CollisionShape2D"},
    {"node_type": "Camera2D", "node_name": "Camera2D"}
  ],
  save=True
)
// { "node_path": "Player", "created": true, "children": ["CollisionShape2D", "Camera2D"],
//   "properties_set": ["position"], "saved": true, "reversible_by": "undo", ... }
```

The assistant can also do the steps separately when one result matters:

```jsonc
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D", node_name="Player")
godot_scene_edit_set_node_property(node_path="Player", property="position", value={"x": 400, "y": 300})
godot_scene_edit_set_node_property(node_path="Player", property="modulate", value="#ff8800")
```

`compose_node` is the create-with-config macro. The primitive
`create_node` only takes `parent_path`, `node_type`, and `node_name`.

## 4. Give the character controls

**You say**

> "Give the character controls so it moves with the arrow keys, and make sure the script is valid."

**Or say it precisely**

> "Write a CharacterBody2D script that uses `Input.get_vector` at speed 300, attach it to Player, and check it parses."

**What happens**

- The assistant writes the GDScript to disk immediately (no scene save needed).
- It attaches the script to the Player.
- It runs a parse check and reports the errors, or confirms the file is clean.
- If a brand-new `class_name` reports an error with `rescan_pending: true`, it re-checks once before changing correct code.

**Under the hood**

```jsonc
godot_enable_toolset(category="scripts")

godot_scripts_write(
  script_path="res://scripts/player.gd",
  content="extends CharacterBody2D\n\n@export var speed: float = 300.0\n\nfunc _physics_process(_delta: float) -> void:\n\tvar direction := Input.get_vector('ui_left', 'ui_right', 'ui_up', 'ui_down')\n\tvelocity = direction * speed\n\tmove_and_slide()\n"
)
// { "script_path": "res://scripts/player.gd", "written": true, ... }

godot_scene_edit_attach_script(node_path="Player", script_path="res://scripts/player.gd")
// { "node_path": "Player", "script_path": "res://scripts/player.gd", "attached": true }

godot_scripts_get_parse_errors(script_path="res://scripts/player.gd")
// { "script_path": "...", "errors": [], "rescan_pending": false }
```

## 5. Make the player collide with the world

**You say**

> "Make the player bump into walls and the floor instead of walking through them."

**Or say it precisely**

> "Give Player a CircleShape2D with radius 24, collision layer 1, and a mask for layers 2 and 3."

**What happens**

- The assistant creates the `CollisionShape2D` and its `CircleShape2D` in one undoable call.
- It sets the body's collision layer and mask.
- It refuses a 2D shape on a 3D body up front, instead of shipping collisionless levels.

**Under the hood**

```jsonc
godot_enable_toolset(category="physics")

godot_physics_setup_collision(
  node_path="Player",
  shape_type="CircleShape2D",
  properties={"radius": 24}
)
// { "node_path": "Player/CollisionShape2D", "shape_type": "CircleShape2D", "created": true, "persisted": true }

godot_physics_set_layers(node_path="Player", layers=[1], mask=[2, 3])
// { "node_path": "Player", "collision_layer": 1, "collision_mask": 6 }
```

A shape is a **resource**. Don't try to build one with
`godot_scene_edit_set_node_property(property="shape", value={"type": "CircleShape2D", ...})`;
that setter only accepts a `res://` resource path or `null`.

## 6. Save and check it sticks

**You say**

> "Save my work so it's still here when I reopen the project — and tell me if anything won't stick."

**What happens**

- The assistant saves the scene and reports the path.
- Every structural mutation already carried a persistence verdict; it reads that verdict rather than assuming.
- If an edit landed inside an instanced scene without Editable Children, it says so and offers the exact fix.

**Under the hood**

```jsonc
godot_scene_edit_save_scene()
// { "saved": true, "path": "res://scenes/main.tscn", "reversible_by": "none" }
```

```jsonc
// success
{ "node_path": "Player", "created": true, "persisted": true }

// live in the editor, lost on save
{
  "node_path": "Relic/Cold/Marker",
  "created": true,
  "persisted": false,
  "reason": "instanced_child_not_editable",
  "hint": "'Relic/Cold' is inside the instanced scene 'Relic', which doesn't have Editable Children enabled — the change shows in the editor but won't be saved. Enable Editable Children on 'Relic', or target a node the scene owns."
}
```

The fix is the call the verdict names:

```jsonc
godot_scene_edit_set_editable_children(node_path="Relic", editable=true)
godot_scene_edit_set_node_property(node_path="Relic/Cold", property="position", value={"x": 10, "y": 0})
```

Other reason tokens: `node_not_owned`, `embedded_in_other_resource`,
`group_from_base_scene`. See [Persistence truth](architecture/persistence.md).

## 7. Preview a delete

**You say**

> "If I remove the old spawner, what breaks? Don't delete it yet."

**What happens**

- The assistant previews the delete: what disappears, and whether the change would persist.
- Nothing changes; the preview carries the same checks the real run will.
- If you approve, it performs the delete with `confirm=true`.

**Under the hood**

```jsonc
godot_scene_edit_delete_node(node_path="OldSpawner", dry_run=true)
// { "node_path": "OldSpawner", "deleted": false, "dry_run": true, "persisted": true, ... }

godot_scene_edit_delete_node(node_path="OldSpawner", confirm=true)
// { "node_path": "OldSpawner", "deleted": true, "persisted": true, ... }
```

Without `confirm=true`, a destructive call refuses with
`PRECONDITION_FAILED` and `required: "confirm"`.

## 8. Run the game and read the errors

**You say**

> "Run the game and tell me if anything's broken."

**What happens**

- The assistant runs the project in a separate headless Godot process.
- It reports errors, warnings, the exit code, and whether the run timed out.
- A game that never quits on its own times out; that is not a crash.

**Under the hood**

```jsonc
godot_enable_toolset(category="runtime")

godot_runtime_run_and_capture(scene="res://scenes/main.tscn", timeout_seconds=5)
// { "ran": true, "exit_code": 0, "timed_out": false, "errors": [], "warnings": [], "output": [] }
```

- `timed_out: true` with `exit_code: null` is a timeout.
- A real crash has a non-zero exit code and an error entry.
- For parse + tree + run + bridge in one call, ask for the "debug workflow"
  (`godot_debug_workflow()`, in `core`).

## 9. Play it and check it works

**You say**

> "Play it and check that the player can actually move and pick up a coin."

**Or say it precisely**

> "Play main.tscn, hold ui_right for a moment, then assert that Player.position.x increased and GameManager.coin_count is at least 1."

**What happens**

- The assistant starts a live play session inside the editor.
- It reads the running game's hierarchy (not the editor's copy), samples the position, and injects input.
- It asserts the resulting state instead of saying "it ran".
- It stops the session when done.

The first time, the assistant also makes sure the `MCPRuntimeProbe` autoload is registered.

**Under the hood**

```jsonc
godot_enable_toolset(category="runtime,input,testing")

godot_inspection_get_project_info()   // confirm MCPRuntimeProbe is in autoloads
godot_runtime_play_scene(scene_path="res://scenes/main.tscn")
// { "playing": true, ... }

godot_runtime_get_game_scene_tree()
// the LIVE game hierarchy, not the editor's copy

godot_runtime_monitor_property(node_path="/root/Main/Player", property="position", samples=30)
godot_runtime_get_property_samples()
// { "ready": true, "samples": [{ "frame": 0, "value": { "x": 400, "y": 300 } }, ...] }

godot_input_simulate_action(action="ui_right", pressed=true)
godot_input_simulate_action(action="ui_right", pressed=false)
godot_input_get_stats()
// { "playing": true, "connected": true, "injected": 2 }
```

```jsonc
godot_testing_assert_node_state(
  node_path="/root/Main/GameManager",
  property="coin_count",
  expected=1,
  op=">="
)
// { "node_path": "...", "property": "coin_count", "expected": 1, "actual": 1, "passed": true }

godot_runtime_stop_scene()
```

While the game is paused at a debugger break, input is refused
(`required: "game_not_breaked"`) and `input_get_stats().injected` stops moving.
That is the pause signal, not a bug.

## 10. Debug a broken player

**You say**

> "The player keeps falling through the floor. Pause the game and tell me what's going on."

**Or say it precisely**

> "Set a breakpoint at player.gd:42, run until it, step over the next line, and evaluate `player.health`."

**What happens**

- The assistant sets the breakpoint, waits for it to fire (or forces a break on the next frame).
- It steps over/into/out and evaluates an expression in the running game.
- It resumes and removes the breakpoint.
- The paused-frame stack is not available on Godot 4.7; the assistant uses global-scope evaluation instead.

**Under the hood**

```jsonc
godot_enable_toolset(category="debugger")

godot_debugger_set_breakpoint(path="res://scripts/player.gd", line=42)
// { "path": "...", "line": 42, "breakpoint_set": true }

godot_debugger_force_break()          // break on the probe's next frame
godot_debugger_step_over()
godot_debugger_evaluate_expression(expression="player.health")
// { "expression": "player.health", "value": 100, "evaluated": true }

godot_debugger_continue_execution()
godot_debugger_remove_breakpoint(path="res://scripts/player.gd", line=42)
```

`evaluate_expression` runs in the **running game's global scope**, not at a
paused frame. `get_stack_frames` and `get_frame_variables` are `UNSUPPORTED` on
Godot 4.7 (#677).

## 11. Change many things at once

**You say**

> "Make all the coins look different."

**Or say it precisely**

> "Set modulate to red on every Area2D under Coins, and tell me whether the batch is undoable."

**What happens**

- The assistant finds the coins, previews the batch, and applies the change.
- It reports the affected nodes, any persistence failures, and whether the batch is undoable.
- Above 20 nodes the undo stack is bypassed for performance; the result says `undoable: false`.

**Under the hood**

```jsonc
godot_enable_toolset(category="batch")

godot_batch_find_nodes_by_type(node_type="Area2D", parent_path="Coins", recursive=True, offset=0, limit=50)
// { "type": "Area2D", "nodes": [...], "count": 3, "total": 3, "returned": 3, "truncated": false }

godot_batch_set_property(
  node_paths=["Coins/Coin1", "Coins/Coin2", "Coins/Coin3"],
  property="modulate",
  value={"r": 1, "g": 0, "b": 0, "a": 1}
)
// { "applied": [...], "count": 3, "undoable": true, "persistence": [...] }
```

For a mix of different operations, `godot_composite_run_commands(commands=[...])`
runs them in one editor round-trip and reports `aborted_at`/`skipped_count` if it
halts early.

## 12. Make it look better

**You say**

> "Make it look better — grass ground, nicer score text, and a hit flash on the player."

**Or say it precisely**

> "Create a TileSet for World/Ground, set the score label font color to gold, and assign a canvas_item flash shader to Player/Sprite2D."

**What happens**

- The assistant enables the matching authoring toolset, creates the resource, and verifies it.
- Shader code is compile-checked before it is assigned.
- Tile, theme, and animation edits are undoable; resource files report their save path.

**Under the hood**

```jsonc
// TileSet + a tile, then place it
godot_enable_toolset(category="tilemap")
godot_tilemap_create_tileset(node_path="World/Ground", save_path="res://tiles/ground.tres", tile_size={"x": 32, "y": 32})
godot_tilemap_add_tileset_atlas_source(texture_path="res://art/ground.png", region_size={"x": 32, "y": 32}, node_path="World/Ground", tileset_path="res://tiles/ground.tres", source_id=0)
godot_tilemap_create_tile(source_id=0, atlas_coords={"x": 0, "y": 0}, node_path="World/Ground", tileset_path="res://tiles/ground.tres")
godot_tilemap_set_cell(node_path="World/Ground", coords={"x": 4, "y": 7}, source_id=0, atlas_coords={"x": 0, "y": 0})
```

```jsonc
// Theme color override
godot_enable_toolset(category="theme_ui")
godot_theme_ui_create(node_path="UI", save_path="res://themes/ui.tres")
godot_theme_ui_set_color(node_path="UI/ScoreLabel", name="font_color", color="#ffd700")

// Shader: write, compile-check, assign
godot_enable_toolset(category="shader")
godot_shader_create(shader_path="res://shaders/flash.gdshader", code="shader_type canvas_item;\nuniform vec4 tint : source_color = vec4(1.0);\nvoid fragment() { COLOR = tint; }\n")
godot_shader_validate(shader_path="res://shaders/flash.gdshader")
// { "ok": true, "errors": [] }
godot_shader_assign_material(node_path="Player/Sprite2D", shader_path="res://shaders/flash.gdshader")

// Animation
godot_enable_toolset(category="animation")
godot_animation_create(node_path="Player", name="idle", length=1.0)
godot_animation_add_track(node_path="Player", animation="idle", track_path="Sprite2D:modulate", track_type="value")
godot_animation_insert_keyframe(node_path="Player", animation="idle", track=0, time=0.0, value="#ffffff")
```

A clean shader compile is a compile verdict, not a visual check.

## 13. Check the game and build it

**You say**

> "Check the game for problems, then build me a web version."

**Or say it precisely**

> "Run validate_project with warnings on scripts and scenes, then export the Web preset to builds/web/index.html."

**What happens**

- The assistant runs the project's validation rules (built-ins plus `res://.mcp/validators/`).
- It reports findings with paths and a next call for each.
- It lists export presets, runs the export, and reports the exit code and artifact path.

**Under the hood**

```jsonc
godot_enable_toolset(category="analysis")
godot_analysis_validate_project(paths=["res://scripts", "res://scenes"], include_warnings=true)
// { "valid": false, "findings": [{ "severity": "error", "path": "res://scripts/x.gd", "message": "...", "next_call": {...} }] }

godot_enable_toolset(category="export")
godot_export_list_presets()
// { "presets": [{ "name": "Web", "platform": "Web", ... }] }

godot_export_project(preset="Web", output_path="builds/web/index.html", confirm=true)
// { "preset": "Web", "output_path": "builds/web/index.html", "exported": true, "exit_code": 0, ... }
```

Project-owned validators live in `res://.mcp/validators/` — see
[Project validators](https://github.com/hybridindie/godot-mcp/tree/main/examples/validators).

## 14. Fix a failure

**You say**

> "That didn't work — read the error and fix it."

**What happens**

- The assistant reads the structured error, not a stack trace.
- `required` names the missing precondition; `hint` says how to satisfy it; `next_call` (when present) is a corrected call it can send as-is.
- It retries only after satisfying the precondition, and it re-reads state after a timed-out mutation before retrying.

**Under the hood**

| Call result | Next call |
|-------------|-----------|
| `unknown tool` | `godot_enable_toolset(category="…")`, then retry |
| `PRECONDITION_FAILED` + `required: "active_scene"` | `godot_scene_edit_open_scene(scene_path="res://scenes/main.tscn")` |
| `PRECONDITION_FAILED` + `required: "confirm"` | `godot_scene_edit_delete_node(node_path="…", dry_run=true)`, then retry with `confirm=true` |
| `PRECONDITION_FAILED` + `required: "consent"` | `godot_describe_tool(tool="godot_scene_edit_delete_node", args={...})`, then pass its `token` as `consent` |
| `PRECONDITION_FAILED` + `required: "editor_ready"` | wait, then `godot_health_check()` until `editor_status` is ready |
| `PRECONDITION_FAILED` + `required: "bridge_connected"` | open Godot + the addon, then `godot_health_check()` |
| `PRECONDITION_FAILED` + `required: "runtime_probe"` | register `MCPRuntimeProbe` as an autoload |
| `PRECONDITION_FAILED` + `required: "play_session"` | `godot_runtime_play_scene(scene_path="…")` |
| `PRECONDITION_FAILED` + `required: "game_not_breaked"` | `godot_debugger_continue_execution()` |
| `PRECONDITION_FAILED` + `required: "godot_version"` | upgrade the editor, or use a tool the version supports |
| `PRECONDITION_FAILED` + `required: "godot_bin"` | install Godot / set `GODOT_MCP_GODOT_BIN` |
| `TIMEOUT` on a mutating tool + `may_have_applied: true` | re-read state before retrying; don't double-apply |
| `RESOURCE_NOT_FOUND` | `godot_inspection_get_scene_tree()`, then use a path it returned |
| `VALIDATION_ERROR` on `godot_project_set_setting` | use the hinted key (`application/run/main_scene`) |
| `persisted: false` + `reason` | act on the hint (e.g. `set_editable_children`, or retarget) |
| `rescan_pending: true` | re-run the parse check once before editing |
| `NON-ZERO EXIT` from a run | read `errors[]`, fix, re-run |
| `RUN TIMED OUT` | if the game never self-quits, pass `expected_timeout=true` to `godot_debug_workflow` |
| `CONSENT_MISMATCH` | re-mint with `godot_describe_tool` using the exact tool + args |
| `EDITOR_BUSY` | wait for import/modal to finish, then retry |

For the full error-code enum and design rules, see
[Errors & recovery](reference-errors.md).

## 15. Undo or roll back

**You say**

> "Undo that. If you can't, get me back to how it was."

**What happens**

- The assistant checks the editor history and undoes the last action.
- It can mark a checkpoint before a risky batch and undo back to it.
- For edits the undo stack does not cover, it takes a VCS snapshot first and restores from it if needed.

**Under the hood**

```jsonc
godot_list_history()
// { "version": 12, "depth": 12, "has_undo": true, "recent": [...] }

godot_checkpoint_create(label="before-batch-refactor")
// { "checkpoint_id": "c3", "current_action": 12, ... }

godot_undo()
// steps back one editor action

godot_checkpoint_restore(checkpoint_id="c3", dry_run=true)
// { "requested": 4, "undone": 0, "complete": false, "dry_run": true, ... }
```

A change the undo stack does not cover reports `reversible_by: "vcs"`; take a
`godot_vcs_snapshot` before large non-undoable edits so `godot_vcs_restore` is
available.

## 16. Go deeper

**You say**

> "Run the full debug workflow on main.tscn, then show me the signal flow, any unused resources, and a before/after diff around the Player. Run the test suite and profile it too."

**What happens**

- The assistant runs parse + tree + headless run + bridge in one report.
- It maps signal connections, finds orphaned resources, and snapshots the Player subtree so a later diff shows exactly what changed.
- It runs the project's test suite and reads the editor/running-game performance monitors.
- This is the same surface an engineer would drive directly — the prompts just compose it.

**Under the hood**

```jsonc
godot_debug_workflow(scene="res://scenes/main.tscn", expected_timeout=true)
// { "findings": [...], "suggestions": [...], ... }

godot_enable_toolset(category="analysis")
godot_analysis_analyze_signal_flow(scene="res://scenes/main.tscn")
godot_analysis_find_unused_resources()

godot_inspection_snapshot_subtree(node_path="Player")
// { "snapshot_id": "s1", ... }
// ... make the change ...
godot_inspection_diff_snapshots(before_id="s1")
// { "added": [...], "removed": [...], "changed": [{ "node": "...", "property": "...", "before": ..., "after": ... }] }

godot_enable_toolset(category="testing")
godot_testing_run_tests(test_dir="res://tests/unit")
// { "passed": 60, "failed": 0, ... }

godot_enable_toolset(category="profiling")
godot_profiling_get_performance_monitors()
// editor + running-game FPS, draw calls, memory
```

When you need to *look* rather than read, the assistant can take both screenshots
and diff them:

```jsonc
godot_editor_capture_screenshot()                 // editor viewport (editor toolset)
godot_runtime_capture_game_screenshot()           // running game (runtime + probe)
godot_testing_compare_screenshots(image_a="<base64>", image_b="<base64>")
```

For a hard bug, combine this with [recipe 10](#10-debug-a-broken-player):
break, step, evaluate in the running game, then resume. The calls are exact;
the prompts can stay as vague as "why is this broken?"
