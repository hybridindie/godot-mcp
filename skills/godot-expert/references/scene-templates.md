# Scene File Templates

## Player scene (CharacterBody2D + Polygon2D body + collision)

```
[gd_scene format=3 uid="uid://example"]

[ext_resource type="Script" path="res://scripts/player.gd" id="1"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 32)

[node name="Player" type="CharacterBody2D"]
collision_layer = 1
collision_mask = 18
script = ExtResource("1")

[node name="Body" type="Polygon2D" parent="."]
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
color = Color(0.2, 0.8, 1, 1)

[node name="Collision" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")

[node name="Camera" type="Camera2D" parent="."]
enabled = true
```

## Enemy scene (CharacterBody2D + chase AI)

```
[gd_scene format=3 uid="uid://example"]

[ext_resource type="Script" path="res://scripts/enemy.gd" id="1"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(28, 28)

[node name="enemy" type="CharacterBody2D"]
collision_layer = 2
collision_mask = 18
script = ExtResource("1")

[node name="Body" type="Polygon2D" parent="."]
polygon = PackedVector2Array(-14, -14, 14, -14, 14, 14, -14, 14)
color = Color(0.9, 0.2, 0.2, 1)

[node name="Collision" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")
```

## Projectile scene (Area2D + lifetime + range)

```
[gd_scene format=3 uid="uid://example"]

[ext_resource type="Script" path="res://scripts/projectile.gd" id="1"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(12, 4)

[node name="projectile" type="Area2D"]
collision_layer = 4
collision_mask = 2
script = ExtResource("1")

[node name="Body" type="Polygon2D" parent="."]
polygon = PackedVector2Array(-6, -2, 6, -2, 6, 2, -6, 2)
color = Color(1, 0.9, 0.2, 1)

[node name="Collision" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")
```

## Main scene (world + player + HUD + overlay)

Node order matters for z-ordering — world first, player after, HUD last:

```
main (Node2D) — has world.gd script
├── Background (Node2D) — tile pool children added at runtime
├── Obstacles (Node2D) — StaticBody2D children added at runtime
├── Player (CharacterBody2D) — has player.gd script, groups=["player"]
│   ├── Body (Polygon2D)
│   ├── Collision (CollisionShape2D)
│   └── Camera (Camera2D)
└── HUD (CanvasLayer) — has hud.gd script
    ├── HealthBar (ProgressBar)
    ├── XPBar (ProgressBar)
    ├── ScoreLabel (Label)
    ├── WaveLabel (Label)
    └── GameOverScreen (Control) — has game_over.gd script, mouse_filter=2
        ├── BG (ColorRect, anchors_preset=15, mouse_filter=2)
        └── VB (VBoxContainer, anchors_preset=8 center)
            ├── Label (Label)
            └── Button (Button)
```

## project.godot input section (WASD + arrows)

```ini
[input]

move_left={
"deadcode":0,
"events":[Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":97,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]}
move_right={
"deadcode":0,
"events":[Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":100,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]}
move_up={
"deadcode":0,
"events":[Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":119,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194320,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]}
move_down={
"deadcode":0,
"events":[Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":83,"key_label":0,"unicode":115,"location":0,"echo":false,"script":null)
, Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194322,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)
]}
```