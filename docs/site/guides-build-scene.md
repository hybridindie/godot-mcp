---
type: index
title: "Build a scene"
description: "Scaffold → nodes → script → collision → save, with previews and persistence verdicts at each step."
created: 2026-09-19
updated: 2026-09-19
---

# Build a scene

The canonical build loop, with the safety machinery visible at each step.

## 1. Scaffold

```
godot_enable_toolset('scene_edit')
godot_scene_edit_create_scene(root_type="Node2D", scene_path="res://scenes/main.tscn")
```

`root_type` accepts **built-in ClassDB node types only** — a custom
`class_name` script is refused (ClassDB can't instantiate script classes). To
root a scene on a custom class: create with the base built-in type, then
`attach_script` the root.

## 2. Compose the tree

```
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D", node_name="Player")
godot_scene_edit_create_node(parent_path="Player", node_type="Polygon2D", node_name="Body")
godot_scene_edit_set_node_property(node_path="Player/Body", property="color", value="#88ffcc")
```

Efficiency lever: several independent operations in one round-trip via
`godot_composite_run_commands` (the editor drains each command in ~one frame)
or `godot_composite_batch_create_nodes` for many same-typed nodes.

## 3. Attach behavior

```
godot_scripts_write(script_path="res://scripts/player.gd", content="extends CharacterBody2D\n…")
godot_scene_edit_attach_script(node_path="Player", script_path="res://scripts/player.gd")
```

Script writes flush to disk immediately (no scene save needed); scene edits
live in editor memory until `godot_scene_edit_save_scene()`.

## 4. Physics

```
godot_enable_toolset('physics')
godot_physics_setup_collision(node_path="Player", shape_type="RectangleShape2D",
                              properties={"size": {"x": 32, "y": 48}})
godot_physics_setup_body(node_path="Player", properties={"mass": 2.0})
godot_physics_set_layers(node_path="Player", layers=[1], mask=[2])
```

`setup_collision` dimension-checks the shape against the body up front — a 2D
shape on a 3D body is refused with a naming hint instead of silently shipping
collisionless levels.

## 5. Verify, then save

```
godot_scripts_get_parse_errors(script_path="res://scripts/player.gd")
godot_scene_edit_save_scene()
```

Parse-clean is necessary, not sufficient — runtime API misuse needs the
headless run (see [verify](guides-verify.md)).

## Reading the persistence verdicts

Every mutation result carries `persisted`/`reason`/`hint`:

- `persisted: true` → the save keeps it.
- `persisted: false, reason: instanced_child_not_editable` → the target is
  inside an instanced scene. Fix: `godot_scene_edit_set_editable_children(node_path="Relic")`
  (then re-apply), or retarget a node the scene owns.
- `persisted: false, reason: node_not_owned` → the node has no owner (e.g.
  added by a `@tool` script); re-create it through the tools so the owner lands.
- Batch results: read `persistence[]` per target and `undoable`.

## Groups & signals

```
godot_scene_edit_add_to_group(node_path="Player", group="player")
godot_scene_edit_connect_signal(source_path="Enemy", signal_name="died",
                                target_path=".", method_name="_on_enemy_died")
```

Both are UndoRedo-wrapped; the signal connection reports `already_connected`
instead of failing on a duplicate.

## Undo

`godot_undo()` steps back the last editor action. Large batches above 20 nodes
bypass the undo stack (`undoable: false` in the result) — plan those.