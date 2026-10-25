---
name: godot-expert
description: "Use for any Godot 4.x game work — writing or fixing GDScript, adding and configuring nodes and scenes, UI/HUD, physics and collision, autoloads, shaders, animation and tests — before you write code or change a scene. Encodes the Godot 4.x engine rules, node-type constraints, rendering order, autoload lifecycle, and MCP tool patterns that prevent the common pitfalls: Control vs Node2D rendering, z-ordering, autoload-children visibility, input interception, type inference, and scene file format."
---

# Godot Expert Developer

Godot 4.x engine rules for building games through the Godot Editor MCP tools. Every
rule here was learned by hitting the bug. This file is the core that applies to all
work; each area has a guide in `references/`. Read the matching guide **before** you
start that kind of work.

Companions: `godot-rules.md` (always-on rules), `godot-getting-started` (version check,
toolset gating, safety), `godot-playtest-and-debug` (run, inspect, debug).

## Small edits: the short path

A one-node or one-property change needs no reference guide:

1. `godot_enable_toolset(category="scene_edit")` (the key is `category`; for scripts use `"scripts"`).
2. `godot_inspection_get_scene_tree()` to find the parent path.
3. `godot_scene_edit_create_node(parent_path=..., node_type=..., node_name=...)`, then
   `godot_scene_edit_set_node_property(...)` for each property.
4. Result not `persisted: true`? Call `godot_scene_edit_save_scene()`.
5. Verify from the editor (`godot_inspection_get_scene_tree()`,
   `godot_inspection_get_node_properties(node_path=...)`), then stop.

Saving rewrites the whole `.tscn`: it drops `load_steps`, adds `unique_id` and reorders
sections. A large `git diff` after a one-node change is normal, not damage, so don't
diff or hand-read the file to verify.

## Read before you build

These are for multi-step work in an area; a single node or property follows the short
path above.

- Before building UI or a HUD (labels, bars, menus, overlays), read [references/ui-hud.md](references/ui-hud.md).
- Before collision, physics bodies or layers/masks, read [references/physics-collision.md](references/physics-collision.md).
- Before writing or running GUT tests, read [references/testing-gut.md](references/testing-gut.md).
- Before hand-editing a `.tscn`, composing scenes, or looking up a scene/project tool, read [references/scene-authoring.md](references/scene-authoring.md).
- Before adding an autoload, a state machine or entity spawning, read [references/autoload-architecture.md](references/autoload-architecture.md).
- Before creating a player, enemy, projectile or main scene from scratch, read [references/scene-templates.md](references/scene-templates.md).
- Before building a TileMap, TileSet or GridMap, read [references/tileset-gridmap.md](references/tileset-gridmap.md).
- Before building a VisualShader graph, read [references/visual-shader.md](references/visual-shader.md).
- Before writing a `.gdshader`, read [references/shader-authoring.md](references/shader-authoring.md).
- Before theming or styling Controls, read [references/theme-styling.md](references/theme-styling.md).
- Before particles, animation tracks, AnimationTree or navigation, read [references/particles-animation.md](references/particles-animation.md).
- Before debugging "it doesn't show / doesn't move / doesn't spawn", read [references/common-bugs.md](references/common-bugs.md).

## 1. Node types and rendering

- `Control` nodes (ColorRect, Label, Button, ProgressBar…) render in **screen space**;
  `Node2D` nodes (Polygon2D, Sprite2D, Camera2D…) render in **world space**. A
  `ColorRect` under a `CharacterBody2D`/`Area2D` does **not** follow the body.
  Entity visuals → `Polygon2D`/`Sprite2D`; HUD → `Control` inside a `CanvasLayer`.
- No image assets? Use `Polygon2D`. In GDScript the polygon takes `Vector2`s:
  `PackedVector2Array([Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)])`.
  In `.tscn` text the flat-float form is valid: `PackedVector2Array(-16, -16, 16, -16, …)`.
- 2D siblings draw in tree order: earlier is underneath. Put Background and Obstacles
  **before** Player; a `CanvasLayer` HUD is always on top. Use `z_index` for explicit order.
- Spawn entities as children of the **scene root** (`get_tree().current_scene`), never on
  a plain-`Node` autoload (no world transform, so they're invisible) or
  `get_tree().root` (a `Window`).

## 2. Input and pause

- A full-screen `Control` (overlay, background `ColorRect`, `anchors_preset = 15`) eats
  all input by default. Set `mouse_filter = Control.MOUSE_FILTER_IGNORE` (`2` in `.tscn`)
  on it; its `Button`s still get clicks.
- Use custom actions (`move_left`…) with WASD + arrows in `project.godot`, not `ui_*`.
  Read with `Input.get_vector("move_left", "move_right", "move_up", "move_down")`.
- `get_tree().paused = true` freezes `PROCESS_MODE_INHERIT` nodes. UI and autoloads that
  must keep working need `process_mode = Node.PROCESS_MODE_ALWAYS`.

## 3. Physics in one paragraph

`collision_layer` is what a body **is**; `collision_mask` is what it **hits** (bitmasks
1, 2, 4, 8, 16…). `CollisionShape2D.shape` is a **resource** property, not a child node:
`godot_scene_edit_set_node_property(node_path='Player/Collision', property='shape', value={'type': 'RectangleShape2D', 'size': {'x': 32, 'y': 32}})`.

## 4. GDScript gotchas

- `var x := expr` fails when the type can't be inferred: group lookups (return `Node`),
  `null`, untyped chains, `load(...).instantiate()`. Annotate:
  `var player: Node2D = get_tree().get_first_node_in_group("player")`,
  `var main: Node = load("res://scenes/main.tscn").instantiate()`.
- Renaming or removing a signal breaks every `connect` to it at runtime
  ("Invalid access to property or key"). Update all connectors in the same change, and
  pin the contract with a test (`get_signal_list()`).
- **Godot 4.8:** a bare string literal is no longer a comment (standalone-expression
  warning). Use `#`. A class can't extend its **own** inner class (`Cyclic inheritance`),
  so move the base class to its own script.
- **Godot 4.6+:** `add_control_to_bottom_panel()` is deprecated in favour of `EditorDock`
  + `add_dock()`. `EditorDock` doesn't exist on 4.4/4.5, so an addon with a 4.4 floor
  resolves it at runtime (`ClassDB.class_exists("EditorDock")`) and keeps the legacy call
  as the fallback.

## 5. Scenes, saving and the MCP tools

- Change scenes and nodes through the MCP scene tools (`godot_scene_edit_create_node`,
  `godot_scene_edit_set_node_property`, `godot_scene_edit_attach_script`). Hand-edit a
  `.tscn` only when it isn't open in the editor, then `godot_scene_edit_reload_scene()`.
- Script writes hit disk immediately. Scene edits persist when the tool result says
  `persisted: true`; otherwise call `godot_scene_edit_save_scene()` (or
  `godot_scene_edit_save_all_scenes()`). `godot_runtime_run_and_capture()` runs the
  **files on disk**, so save first.
- `godot_scripts_get_parse_errors()` after every script write. `rescan_pending: true`
  right after a new `class_name` is stale cache; re-check before "fixing" correct code.
- Guessing a property or method? `godot_describe_class("Tween")` gives the exact names,
  Variant types and default JSON shapes.
- Read the honesty fields: `godot_composite_run_commands` stops at the first error, so
  check `aborted_at`/`skipped_count` (trailing commands, like a final save, did **not**
  run). `godot_batch_set_property` on more than 20 nodes returns `undoable: false`, so undo
  won't revert it. `godot_project_set_setting` refuses unknown keys with a did-you-mean.
- Changing `project.godot` on disk (input actions, autoloads) needs Project → Reload
  Current Project before the editor sees it.
- Live inspection or input during play needs the `MCPRuntimeProbe` autoload (see
  `godot-playtest-and-debug`).

## 6. Checklist before you report done

- [ ] Background/Obstacles before Player; entity visuals are Node2D, not Control
- [ ] Spawned entities go under the scene root, not an autoload
- [ ] Full-screen overlays have `mouse_filter = IGNORE`
- [ ] Every script parses (`godot_scripts_get_parse_errors()`); shaders validate
      (`godot_shader_validate(shader_path=...)`); API misuse only shows at runtime
      (`godot_runtime_run_and_capture()`)
- [ ] GUT tests pass when the task involves tests (`godot_testing_run_tests()`)
- [ ] Scene saved (or `persisted: true`), and the result read back from the scene tree
