---
type: index
title: "Build a scene"
description: "Scaffold → nodes → script → collision → save, with previews and persistence verdicts at each step."
created: 2026-09-19
updated: 2026-10-12
---

# Build a scene

The canonical build loop. You prompt in plain language; the assistant makes the editor
calls and hands you the honest verdicts.

## 1. Scaffold

You: *"Scaffold a main scene."*

The assistant enables scene editing and creates a root scene. The root must be a **built-in**
node type (e.g. `Node2D`) — a custom `class_name` is refused, because the editor can't
instantiate script classes. To root a scene on a custom class, have the assistant create it
with the base built-in type, then attach the script to the root.

```jsonc
godot_enable_toolset(category="scene_edit")
godot_scene_edit_create_scene(scene_path="res://scenes/main.tscn", root_type="Node2D")
// { "scene_path": "res://scenes/main.tscn", "root_type": "Node2D", "created": true, ... }
```

## 2. Compose the tree

You: *"Add a Player with a visible Body shape."*

The assistant adds the nodes and sets their properties — node types, names, and values — all
in your live scene. For several independent operations, ask it to **batch** them: many
commands run in a single editor round-trip (the editor drains each in about a frame), which is
far faster than one call per node.

```jsonc
godot_composite_compose_node(
  parent_path=".", node_type="CharacterBody2D", node_name="Player",
  properties={"position": {"x": 400, "y": 300}},
  children=[
    {"node_type": "CollisionShape2D", "node_name": "CollisionShape2D"},
    {"node_type": "Camera2D", "node_name": "Camera2D"}
  ])
// { "node_path": "Player", "created": true, "children": ["CollisionShape2D", "Camera2D"], ... }
```

## 3. Attach behavior

You: *"Give the Player a movement script."*

Script writes flush straight to disk (no scene save needed), so the assistant writes the
script, attaches it, and the behavior is live in your editor immediately. Scene *edits*, by
contrast, stay in the editor's memory until the scene is saved (step 5).

```jsonc
godot_enable_toolset(category="scripts")
godot_scripts_write(script_path="res://scripts/player.gd", content="extends CharacterBody2D\n...")
godot_scene_edit_attach_script(node_path="Player", script_path="res://scripts/player.gd")
// { "node_path": "Player", "script_path": "res://scripts/player.gd", "attached": true }
```

## 4. Physics

You: *"Give the Player collision so it stands on floors."*

The assistant sets the collision shape, body, and layers. Godot types arrive as plain JSON —
a `Vector2` size is `{"x": 32, "y": 48}` — and it dimension-checks the shape against the body
up front: a 2D shape on a 3D body is refused with a naming hint, instead of silently shipping
collisionless levels.

```jsonc
godot_enable_toolset(category="physics")
godot_physics_setup_collision(node_path="Player", shape_type="CircleShape2D", properties={"radius": 24})
// { "node_path": "Player/CollisionShape2D", "shape_type": "CircleShape2D", "created": true, "persisted": true }
godot_physics_set_layers(node_path="Player", layers=[1], mask=[2, 3])
// { "node_path": "Player", "collision_layer": 1, "collision_mask": 6 }
```

## 5. Verify, then save

You: *"Check the script parses, then save the scene."*

A clean parse is necessary but **not sufficient** — runtime API misuse only shows up when the
game actually runs, so ask for a headless run too (see [Verify your work](guides-verify.md)).
Then save.

```jsonc
godot_scripts_get_parse_errors(script_path="res://scripts/player.gd")
// { "errors": [], "rescan_pending": false }

godot_enable_toolset(category="runtime")
godot_runtime_run_and_capture(scene="res://scenes/main.tscn", timeout_seconds=5)
// { "exit_code": 0, "timed_out": false, "errors": [], "warnings": [] }

godot_scene_edit_save_scene()
// { "saved": true, "path": "res://scenes/main.tscn", "reversible_by": "none" }
```

## Reading the persistence verdicts

Every mutation result carries a **persistence verdict** — whether the save will really keep
the change:

- `persisted: true` → the save keeps it.
- `persisted: false, reason: instanced_child_not_editable` → the target is inside an instanced
  scene. Fix: ask the assistant to enable Editable Children on that scene (then re-apply), or
  to target a node the scene owns.
- `persisted: false, reason: node_not_owned` → the node has no owner (e.g. added by a `@tool`
  script); re-create it through the tools so the owner lands.
- Batch results: read `persistence[]` per target, and `undoable`.

## Groups & signals

You: *"Put the Player in the `player` group and connect the Enemy's `died` signal."*

Both are undoable, and a signal connection that already exists reports `already_connected`
instead of failing on the duplicate.

```jsonc
godot_scene_edit_add_to_group(node_path="Player", group="player")
godot_scene_edit_connect_signal(
  source_path="Enemy", signal_name="died", target_path="GameManager", method_name="_on_enemy_died")
// { "connected": true } — or { "already_connected": true }
```

## Undo

Ask the assistant to undo and it steps back the last editor action. Large batches above 20
nodes bypass the undo stack (the result says `undoable: false`) — plan those.

```jsonc
godot_undo()
// { "undone": 1, "last_action": "create_node 'Player'", ... }
```

Next: [Play-test & debug](guides-playtest-debug.md), or [Verify your work](guides-verify.md).
