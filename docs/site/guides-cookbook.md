---
type: index
title: "Cookbook: agent → Godot examples"
description: "Copy-ready MCP call/response recipes for the whole loop — inspect, build, script, physics, save, preview, run, play-test, debug, batch, authoring, validate, and recover."
created: 2026-11-05
updated: 2026-11-20
---

# Cookbook: agent → Godot examples

These are the calls an agent actually makes, with the result fields that matter.
Every tool name and parameter below is pinned against the live schema by
`tests/unit/test_docs_examples.py`; if a tool changes, this page fails the suite
instead of quietly teaching the wrong call.

For one continuous build instead of short recipes, use the
[Full walkthrough](guides-walkthrough.md).

::: info Gating
Only `core` + `inspection` are on by default. Each recipe names the toolset to
enable first: `godot_enable_toolset(category="scene_edit")`. The enable result
includes the newly enabled tools and their input schemas, so a client that
never refreshes its registry can still call them.
:::

## 1. Orient and enable

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

- If `bridge_connected` is `false`, open Godot with the addon enabled and re-check.
- If a call says `unknown tool`, the toolset is not enabled — enable it, then retry.
- `next_steps` usually names the fix for a broken setup.

## 2. Inspect before you edit

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

Node paths are **scene-relative** (`.` for the root, `Player/Weapon` below it).
Pass them back verbatim; do not rebuild them by walking the tree.

## 3. Build a configured node in one round-trip

```jsonc
godot_composite_compose_node(
  parent_path=".",
  node_type="CharacterBody2D",
  node_name="Player",
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

The primitive form is equivalent — useful when one step needs its own result:

```jsonc
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D", node_name="Player")
godot_scene_edit_set_node_property(node_path="Player", property="position", value={"x": 400, "y": 300})
godot_scene_edit_set_node_property(node_path="Player", property="modulate", value="#ff8800")
```

`compose_node` is the **create-with-config** tool. `create_node` only takes
`parent_path`, `node_type`, and `node_name`; it has no `properties` or
`script_path` parameters.

## 4. Write, attach, and parse-check a script

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

Scripts flush to disk immediately. Scene edits stay in the editor until
`godot_scene_edit_save_scene()`. If a fresh `class_name` reports a parse error
with `rescan_pending: true`, re-check once before changing correct code.

## 5. Physics and collision

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

Do **not** try to build a shape with
`godot_scene_edit_set_node_property(property="shape", value={"type": "CircleShape2D", ...})`.
A shape is a resource; `physics_setup_collision` creates the node and its
shape in one undoable call, and rejects a 2D shape on a 3D body.

## 6. Save and read the persistence verdict

```jsonc
godot_scene_edit_save_scene()
// { "saved": true, "path": "res://scenes/main.tscn", "reversible_by": "none" }
```

Every structural mutation reports whether a save will keep it:

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

## 7. Preview a destructive edit, then confirm

```jsonc
godot_scene_edit_delete_node(node_path="OldSpawner", dry_run=true)
// { "node_path": "OldSpawner", "deleted": false, "dry_run": true, "persisted": true, ... }

godot_scene_edit_delete_node(node_path="OldSpawner", confirm=true)
// { "node_path": "OldSpawner", "deleted": true, "persisted": true, ... }
```

Without `confirm=true`, a destructive call refuses with
`PRECONDITION_FAILED` and `required: "confirm"`. A preview sends nothing and
carries the same persistence verdict the real run will.

## 8. Headless verification

```jsonc
godot_enable_toolset(category="runtime")

godot_runtime_run_and_capture(scene="res://scenes/main.tscn", timeout_seconds=5)
// { "ran": true, "exit_code": 0, "timed_out": false, "errors": [], "warnings": [], "output": [] }
```

- `timed_out: true` is **not** a crash — a game that never self-quits always
  times out. Read `errors`/`warnings` as the verdict.
- `exit_code: null` with `timed_out: true` is a timeout; a real crash has a
  non-zero exit code and an error entry.
- For parse + tree + run + bridge in one call, use `godot_debug_workflow()`
  (in `core`).

## 9. Live play-test: play, inspect, input, assert

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
// { "injected": 2, ... }
```

Then assert the behavior, not just that it ran:

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

## 10. Break, inspect, and step

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
paused frame. The paused-frame stack (`get_stack_frames`) and variables
(`get_frame_variables`) are `UNSUPPORTED` on Godot 4.7 (#677) — they return a
structured error, not an empty list.

## 11. Batch refactor with honest undo semantics

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

A batch above 20 nodes reports `undoable: false` — plan those. For a mix of
different operations, use `godot_composite_run_commands(commands=[...])`; it
reports `aborted_at`/`skipped_count` when it halts early and enforces each
sub-command's own safety class.

## 12. Author a resource

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
godot_shader_assign_material(node_path="Player/Sprite2D", shader_path="res://shaders/flash.gdshader")

// Animation
godot_enable_toolset(category="animation")
godot_animation_create(node_path="Player", name="idle", length=1.0)
godot_animation_add_track(node_path="Player", animation="idle", track_path="Sprite2D:modulate", track_type="value")
godot_animation_insert_keyframe(node_path="Player", animation="idle", track=0, time=0.0, value="#ffffff")
```

Shader code is validated by the engine before assignment; a `shader_validate`
result is a compile verdict, not a visual check.

## 13. Validate and export

```jsonc
godot_enable_toolset(category="analysis")
godot_analysis_validate_project(paths=["res://scripts", "res://scenes"], include_warnings=true)
// { "valid": false, "findings": [{ "severity": "error", "path": "res://scripts/x.gd", "message": "...", "next_call": {...} }] }

godot_enable_toolset(category="export")
godot_export_list_presets()
godot_export_project(preset="Web", output_path="builds/web/index.html", confirm=true)
// { "preset": "Web", "output_path": "...", "exit_code": 0, "succeeded": true }
```

`validate_project` also runs project-owned rules under
`res://.mcp/validators/` — see [Project validators](https://github.com/hybridindie/godot-mcp/tree/main/examples/validators).

## 14. Recovery cookbook

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

## 15. Undo and reversibility

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

Checkpoints cover editor history. A change the undo stack does not cover
reports `reversible_by: "vcs"`; take a `godot_vcs_snapshot` before large
non-undoable edits so `godot_vcs_restore` is available.
