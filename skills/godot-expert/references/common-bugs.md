# Common Bugs and Solutions

Every bug below was hit during development of the survivors example game.
Each has a symptom, root cause, and fix.

---

## Bug: Sprites not showing (ColorRect as child of Node2D)

**Symptom:** Player, enemy, projectile, or gem has a visible node in the
scene tree but nothing renders on screen.

**Root cause:** `ColorRect` is a `Control` node — it renders in screen/UI
space, not 2D world space. As a child of `CharacterBody2D` or `Area2D` (both
`Node2D`), it doesn't inherit the parent's world transform.

**Fix:** Replace `ColorRect` with `Polygon2D`:
```gdscript
var poly := Polygon2D.new()
poly.polygon = PackedVector2Array([
    Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)
])
poly.color = Color(0.2, 0.8, 1.0, 1.0)
body.add_child(poly)
```

---

## Bug: Background covers the player

**Symptom:** The player is in the scene tree but is hidden behind the
background tiles.

**Root cause:** In Godot 2D, later siblings render on top. If `Background`
is after `Player` in the scene tree, the background draws over the player.

**Fix:** Reorder the scene tree so world layers come first:
```
main (Node2D)
├── Background (Node2D)   ← drawn first (bottom)
├── Obstacles (Node2D)
├── Player (CharacterBody2D)  ← drawn on top of world
└── HUD (CanvasLayer)     ← screen space, always on top
```

---

## Bug: Enemies are invisible (autoload children don't render)

**Symptom:** Enemies spawn (they're in the scene tree, they deal damage)
but their sprites are invisible.

**Root cause:** The GameManager autoload is `extends Node` (not `Node2D`).
`add_child(enemy)` on a plain `Node` gives the enemy no 2D world transform
context, so `Polygon2D` children don't render.

**Fix:** Add entities to the scene root, not the autoload:
```gdscript
func _get_world() -> Node2D:
    var scene: Node = get_tree().current_scene
    if scene is Node2D:
        return scene as Node2D
    return null

# Spawn:
var world := _get_world()
if world:
    world.add_child(enemy)
```

---

## Bug: Start menu shows but SPACE does nothing

**Symptom:** The game-over/start overlay is visible with "Press SPACE"
but pressing SPACE/Enter does nothing. The game never starts.

**Root cause:** The full-screen `Control` overlay (and its `ColorRect` BG)
intercept all input events before they reach `GameManager._unhandled_input`.
The UI "eats" the input.

**Fix:** Set `mouse_filter = IGNORE` on the overlay and BG:
```gdscript
func _ready() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
```
In `.tscn`: `mouse_filter = 2` on both the `Control` and `ColorRect`.

---

## Bug: WASD doesn't work, only arrow keys

**Symptom:** Movement works with arrow keys but not WASD.

**Root cause:** The player script uses `ui_left`/`ui_right`/`ui_up`/`ui_down`
which are Godot's built-in arrow-key actions. No WASD mapping exists.

**Fix:** Add custom `move_left`/`move_right`/`move_up`/`move_down` input
actions to `project.godot` under `[input]`, then reload the project.

---

## Bug: Parse error — "Cannot infer the type of variable"

**Symptom:** Script fails to load with:
```
SCRIPT ERROR: Parse Error: Cannot infer the type of "dir" variable
because the value doesn't have a set type.
```

**Root cause:** Godot 4.7's `:=` type inference fails when the right-hand
side involves an untyped value (e.g., from `get_first_node_in_group()` which
returns `Node`, or `null`).

**Fix:** Use explicit type annotations:
```gdscript
# ❌:
var player := get_tree().get_first_node_in_group("player")
var best := null

# ✅:
var player: Node2D = get_tree().get_first_node_in_group("player")
var best: Node2D = null
```

---

## Bug: Parse error — PackedVector2Array constructor

**Symptom:**
```
No constructor of "PackedVector2Array" matches the signature
"PackedVector2Array(float, float, float, float, ...)"
```

**Root cause:** In GDScript, `PackedVector2Array()` takes `Vector2`
objects, not flat floats. (The `.tscn` text format does accept flat floats.)

**Fix:**
```gdscript
# ❌:
poly.polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)

# ✅:
poly.polygon = PackedVector2Array([
    Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)
])
```

---

## Bug: "Invalid access to property 'game_over'" after signal rename

**Symptom:**
```
Invalid access to property or key 'game_over' on a base object
of type 'Node (game_manager.gd)'
```

**Root cause:** A signal was removed/renamed on the GameManager, but another
script (e.g., `hud.gd`) still connects to the old signal name. The editor's
in-memory copy was updated but the on-disk file wasn't (or vice versa).

**Fix:**
1. Update every script that connects to the signal
2. `cmd_save_all_scenes` after `cmd_write_script` to flush to disk
3. Write a test that pins the signal contract:
```gdscript
func test_old_signal_removed() -> void:
    var sigs := gm.get_signal_list()
    for sig in sigs:
        assert_ne(sig["name"], "game_over", "old signal should be removed")
```

---

## Bug: Background doesn't fill screen at higher resolution

**Symptom:** At 1920x1080 the checkerboard tiles don't cover the full
screen — there's empty space at the edges.

**Root cause:** The tile pool was sized with a hardcoded `VIEW_RADIUS=12`
(1600px wide) that worked at 1280x720 but is too small for 1920x1080.

**Fix:** Compute the radius from the actual viewport:
```gdscript
func _calc_view_radius() -> void:
    var vp := get_viewport().get_visible_rect().size
    var zoom := Vector2.ONE
    var cam := get_viewport().get_camera_2d()
    if cam:
        zoom = cam.zoom
    _view_radius_x = int(ceil((vp.x / zoom.x) / TILE_SIZE / 2.0)) + 2
    _view_radius_y = int(ceil((vp.y / zoom.y) / TILE_SIZE / 2.0)) + 2
```

---

## Bug: Overlay appears but has zero size

**Symptom:** The game-over overlay is "visible" (visible=true) but nothing
renders — no text, no button.

**Root cause:** The VBoxContainer has `offset_left = -100` and
`offset_right = -100` — zero width. The BG ColorRect has no anchors — zero
size. Both are technically visible but render nothing.

**Fix:** Center the VBoxContainer with anchors and give it explicit size:
```
[node name="VB" type="VBoxContainer"]
anchors_preset = 8  # center
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -150.0
offset_top = -80.0
offset_right = 150.0
offset_bottom = 80.0
```

---

## Bug: GUT tests hang on `await wait_for_signal`

**Symptom:** GUT test suite hangs / times out when a test does
`await wait_for_signal(node.ready, 1.0)`.

**Root cause:** `_ready` fires synchronously on `add_child` for simple
nodes — the signal has already been emitted by the time `await` is called.

**Fix:** Don't await `ready` for nodes that don't need it:
```gdscript
func before_each() -> void:
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)
    # _ready fires synchronously — no await needed
```