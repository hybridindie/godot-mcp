---
name: godot-mcp-build-a-scene
description: Build or edit a Godot scene through the godot-mcp server — create/open a scene, add and position nodes, attach GDScript, add collision, then save and verify. Use when the user wants to scaffold or modify a Godot .tscn scene via godot-mcp. Triggers on "build a Godot scene", "add a node in Godot", "create a scene", "attach a script to a node", "set up a player scene", "edit the scene tree".
---

# godot-mcp: build a scene

Scaffold a scene with the `scene_edit` and `scripts` toolsets. If you haven't verified the bridge or the gating model, read `godot-mcp-getting-started` first. The server's `/mcp__godot-mcp__build_scene` prompt is the parameterized version of this recipe.

## 1. Enable the toolsets

```
godot_enable_toolset('scene_edit')
godot_enable_toolset('scripts')
godot_enable_toolset('physics')    # only if you need collision
```

## 2. Create or open the scene

```
godot_scene_edit_create_scene(scene_path='res://scenes/main.tscn', root_type='Node2D')
# or, if it already exists:
godot_scene_edit_open_scene(scene_path='res://scenes/main.tscn')
```

## 3. Add and position nodes

`parent_path='.'` is the scene root. Position via a typed property value.

```
godot_scene_edit_create_node(parent_path='.', node_type='Sprite2D', node_name='Player')
godot_scene_edit_set_node_property(node_path='./Player', property='position', value={'x': 64, 'y': 64})
```

## 4. Attach a script

```
godot_scripts_write(script_path='res://scripts/player.gd', content='extends Sprite2D\n...')
godot_scene_edit_attach_script(node_path='./Player', script_path='res://scripts/player.gd')
```

## 5. Add collision (optional)

```
godot_physics_setup_collision(
    node_path='./Player',
    collision_node_type='CollisionShape2D',
    shape_type='CircleShape2D',
    properties={'radius': 32})
```

## 6. Save and verify

```
godot_scene_edit_save_scene()
godot_inspection_get_scene_tree(max_depth=2)     # confirm the hierarchy
godot_scripts_get_parse_errors()                 # confirm scripts compile
```

## Safety

- Preview any uncertain change with `dry_run=True` before committing it.
- Destructive ops (`godot_scene_edit_delete_node`, `godot_scene_edit_reload_scene`) need `confirm=True`.
- For the same property across many nodes, switch to the `batch` toolset and preview with `dry_run` first.
