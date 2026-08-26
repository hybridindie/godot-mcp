# Scene File (.tscn) Authoring

## Format overview

A `.tscn` file is a text-based Godot scene. Three block types:

```
[gd_scene format=3 uid="uid://b5mosf1awod8s"]

[ext_resource type="Script" path="res://scripts/player.gd" id="1_abc"]
[ext_resource type="Script" path="res://scripts/hud.gd" id="2_def"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 32)

[node name="main" type="Node2D"]
script = ExtResource("1_jyhfs")

[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
collision_mask = 18
script = ExtResource("1_sugp2")

[node name="Body" type="Polygon2D" parent="Player"]
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
color = Color(0.2, 0.8, 1, 1)

[node name="Collision" type="CollisionShape2D" parent="Player"]
shape = SubResource("Rect_1")
```

### Block types

| Block | Purpose | Example |
|-------|---------|---------|
| `[gd_scene]` | Header with format version + UID | Required first line |
| `[ext_resource]` | External file reference (scripts, textures, scenes) | `path="res://..."` |
| `[sub_resource]` | Inline resource (shapes, materials) | Defined before nodes that use it |
| `[node]` | A node in the scene tree | `parent="."` = child of root |

### Node properties

```
[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
collision_layer = 1
collision_mask = 18
script = ExtResource("1_sugp2")
```

- `parent="."` = child of the scene root
- `parent="Player"` = child of the Player node
- `groups=["player"]` = the node's groups
- `script = ExtResource("id")` = reference to an ext_resource
- `shape = SubResource("id")` = reference to a sub_resource
- `unique_id = 123456789` = Godot's internal node ID (auto-generated)

---

## Text format vs GDScript syntax

### PackedVector2Array

**In .tscn (flat floats):**
```
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
```

**In GDScript (Vector2 objects):**
```gdscript
poly.polygon = PackedVector2Array([
    Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)
])
```

### Colors

Both formats use `Color(r, g, b, a)`:
```
color = Color(0.2, 0.8, 1, 1)     # .tscn
poly.color = Color(0.2, 0.8, 1, 1)  # GDScript
```

### Vector2

```
position = Vector2(20, 50)         # .tscn
node.position = Vector2(20, 50)    # GDScript
```

---

## Editing scenes: disk vs bridge

### Via the bridge (live editor)

Use when the editor is open and connected:

```python
{"command": "cmd_create_node", "params": {"parent_path": ".", "node_type": "CharacterBody2D", "name": "Player"}}
{"command": "cmd_set_node_property", "params": {"node_path": "Player", "property": "collision_layer", "value": 1}}
{"command": "cmd_attach_script", "params": {"node_path": "Player", "script_path": "res://scripts/player.gd"}}
{"command": "cmd_save_scene"}
```

**Critical:** `cmd_write_script` updates the editor's in-memory copy but
does NOT flush to disk. Always call `cmd_save_scene` or
`cmd_save_all_scenes` after writing scripts.

### On disk (no editor needed)

Use when the editor is closed or for bulk changes:

1. Edit the `.tscn` file directly
2. Edit `project.godot` if needed
3. Reopen/reload the project in Godot

**When editing on disk:** The editor won't pick up changes until you
reload (Project → Reload Current Project). This is required for
`project.godot` changes (input actions, autoloads, resolution).

---

## Common scene patterns

### CollisionShape2D with RectangleShape2D

```
[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 32)

[node name="Collision" type="CollisionShape2D" parent="Player"]
shape = SubResource("Rect_1")
```

**Don't** add `RectangleShape2D` as a child node — it's a resource.

### Camera2D

```
[node name="Camera" type="Camera2D" parent="Player"]
enabled = true
```

As a child of the player, it automatically follows.

### Groups

```
[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
```

Or via the bridge:
```python
{"command": "cmd_add_to_group", "params": {"node_path": "Player", "group": "player"}}
```

### Node ordering for z-ordering

**Node order in the file = tree order = render order (2D).** Earlier
siblings draw first (underneath):

```
[node name="Background" type="Node2D" parent="."]    ← bottom
[node name="Obstacles" type="Node2D" parent="."]
[node name="Player" type="CharacterBody2D" parent="."]  ← on top
[node name="HUD" type="CanvasLayer" parent="."]          ← screen space
```

---

## .uid files

Godot 4.6+ generates `.gd.uid` files alongside each script. These contain
a unique identifier for the script resource. They're safe to commit (small,
one line). If missing, Godot regenerates them on import.