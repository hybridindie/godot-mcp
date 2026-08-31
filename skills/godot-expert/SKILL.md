---
name: godot-expert
description: "Use when building or modifying a Godot 4.x game through the godot-mcp tools — creating scenes, nodes, scripts, physics, UI, or debugging rendering/input/collision issues. Encodes the Godot 4.x engine rules, node-type constraints, rendering order, autoload lifecycle, and MCP tool patterns that an expert Godot developer knows. Prevents the common pitfalls: Control vs Node2D rendering, z-ordering, autoload-children visibility, input interception, type inference, and scene file format."
---

# Godot Expert Developer

Expert knowledge for building Godot 4.x games through the godot-mcp tools.
Every rule below was learned the hard way — by hitting the bug, debugging it,
and writing a test to pin it.

**Companion skills** (read these first for the MCP workflow, not the engine rules):
- `godot-getting-started` — bridge connection, toolset gating, safety classes
- `godot-playtest-and-debug` — runtime play-test, input simulation, debugging

This skill covers the **engine knowledge** that prevents bugs. Those skills
cover **how to call the tools**. Use them together.

## When to use

- Creating scenes, nodes, or scripts via the MCP bridge
- Debugging "sprite not showing", "input not working", "enemy not spawning"
- Setting up physics layers/masks, collision shapes, or UI overlays
- Writing GDScript that parses cleanly on Godot 4.7+
- Structuring a game project (autoloads, scene composition, state machines)

## When NOT to use

- Modifying the godot-mcp server itself (use the architecture/rules instead)
- Python-side work (models, tools, bridge, tests)
- Non-Godot projects

---

## 1. Node types and rendering (the #1 source of bugs)

### Control vs Node2D — where things render

**Rule:** `Control` nodes (ColorRect, Label, Button, ProgressBar, etc.) render
in **screen space** (the CanvasLayer/UI layer). `Node2D` nodes (Polygon2D,
Sprite2D, Camera2D, etc.) render in **2D world space**.

**Critical:** A `ColorRect` child of a `CharacterBody2D` or `Area2D` will NOT
render at the parent's world position. It renders as a UI element at its
offset coordinates, detached from the world transform.

**Do this:**
- For game-entity visuals (player, enemy, projectile, gem), use `Polygon2D`
  or `Sprite2D` — these are `Node2D` and inherit the parent's world transform.
- For HUD/UI (health bars, labels, overlays), use `Control` nodes inside a
  `CanvasLayer`.

**Don't do this:**
- ❌ `ColorRect` as a child of `CharacterBody2D` for the player body
- ❌ `ColorRect` as a child of `Area2D` for a pickup visual
- ❌ Any `Control` node as a child of a `Node2D` physics body expecting it to
  render in world space

### Polygon2D — the no-asset colored shape

When you have no image assets, use `Polygon2D` with a `PackedVector2Array`:

```gdscript
var poly := Polygon2D.new()
poly.polygon = PackedVector2Array([
    Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)
])
poly.color = Color(0.2, 0.8, 1.0, 1.0)
body.add_child(poly)
```

In `.tscn` text format, the same polygon uses flat floats:
```
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
```

### Rendering order (z-ordering)

**Rule:** In Godot 2D, siblings render in tree order — earlier siblings
draw first (underneath), later siblings draw on top.

**Correct scene tree order for a game:**
```
main (Node2D)
├── Background (Node2D)      ← drawn first (bottom layer)
├── Obstacles (Node2D)       ← drawn second
├── Player (CharacterBody2D) ← drawn third (on top of world)
└── HUD (CanvasLayer)        ← always on top (screen space)
```

**Don't do this:**
- ❌ Put `Background` after `Player` — the background covers the player
- ❌ Put `Obstacles` after `Player` — obstacles cover the player

**For dynamically spawned entities** (enemies, projectiles, gems):
- Add them as children of the main scene root (`Node2D`), NOT the autoload
- They render in the order they're added; newer entities draw on top of
  older ones. Use `z_index` if you need explicit control.

---

## 2. Autoloads and entity spawning

### The autoload-children rendering trap

**Rule:** `Polygon2D`, `Sprite2D`, and other `Node2D` visual nodes only render
when they're inside a `Node2D`/`CanvasItem` subtree with a world transform. An
autoload that is a plain `Node` (not `Node2D`) provides no 2D world context.

**Critical:** If your GameManager autoload is `extends Node` and you call
`add_child(enemy)` on it, the enemy's `Polygon2D` body will be **invisible** —
it exists in the tree but has no world-space render context.

**Do this:**
```gdscript
func _get_world() -> Node2D:
    var scene: Node = get_tree().current_scene
    if scene is Node2D:
        return scene as Node2D
    return null

func _spawn_enemy(player: Node2D) -> void:
    var world := _get_world()
    if world == null:
        return
    var enemy := ENEMY_SCENE.instantiate()
    world.add_child(enemy)        # ← add to the scene root, not the autoload
    enemy.global_position = pos
```

**Don't do this:**
- ❌ `add_child(enemy)` on a `Node` autoload — children won't render
- ❌ `get_tree().root.add_child(enemy)` — the real root is a `Window`, not a `Node2D`

### Autoload state persistence

**Rule:** Autoload singletons persist across scene reloads. Their state
(variables, timers, signals) is NOT reset when you call
`get_tree().reload_current_scene()`.

**Do this:** Add an explicit `start_game()` / `reset()` method that clears
state:
```gdscript
func start_game() -> void:
    # Clear leftover entities
    for e in get_tree().get_nodes_in_group("enemies"):
        e.queue_free()
    # Reset state
    score = 0
    wave = 1
    spawn_timer = 0.0
    # Reset player
    var player := get_tree().get_first_node_in_group("player")
    if player:
        player.health = 100.0
        player.global_position = Vector2.ZERO
```

---

## 3. Input handling

### The UI-overlay input trap

**Rule:** `Control` nodes that cover the screen (a full-screen overlay, a
`ColorRect` background, a `Control` with `anchors_preset = 15`) will
**intercept all input events** before they reach `_unhandled_input` on
autoloads or other nodes. The game appears frozen — no keys work, no
movement, no state transitions.

**Symptom:** The start menu shows, but pressing SPACE/Enter does nothing.
The game never transitions from MENU to PLAYING.

**Do this:**
- Set `mouse_filter = Control.MOUSE_FILTER_IGNORE` on the overlay `Control`
  and its `BG` ColorRect so they render visually but don't block input.
- The `Button` inside the overlay keeps its own `mouse_filter` (default
  `STOP`) so it still receives clicks.

```gdscript
func _ready() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE  # don't block input
    # ... connect signals ...
```

In `.tscn`:
```
[node name="GameOverScreen" type="Control" parent="HUD"]
mouse_filter = 2  # IGNORE
```

**Don't do this:**
- ❌ Full-screen `Control` with default `mouse_filter` (STOP) covering the
  game — it eats all input
- ❌ `ColorRect` BG with default `mouse_filter` on a full-screen overlay

### Custom input actions

**Rule:** Don't rely on `ui_left`/`ui_right`/`ui_up`/`ui_down` for game
movement — they're arrow-key defaults and don't include WASD. Define custom
input actions in `project.godot` under `[input]`.

**Required for WASD:**
```ini
[input]
move_left={...events: [Key A, Left Arrow]...}
move_right={...events: [Key D, Right Arrow]...}
move_up={...events: [Key W, Up Arrow]...}
move_down={...events: [Key S, Down Arrow]...}
```

Then in GDScript:
```gdscript
var input_dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
```

**Note:** Changing `project.godot` on disk requires a project reload
(Project → Reload Current Project) for the editor to pick up new input
actions.

### Pause and the process mode

**Rule:** `get_tree().paused = true` freezes all nodes with
`process_mode = PROCESS_MODE_INHERIT` (the default). To keep UI responsive
while paused, set the overlay's `process_mode = PROCESS_MODE_ALWAYS`:

```gdscript
func _ready() -> void:
    process_mode = Node.PROCESS_MODE_ALWAYS
```

For `_unhandled_input` to fire while paused, the autoload also needs
`PROCESS_MODE_ALWAYS`.

---

## 4. Collision layers and masks

### Layer/mask convention

| Bit | Layer | Who uses it |
|-----|-------|-------------|
| 1 | Player | `CharacterBody2D` player |
| 2 | Enemies | `CharacterBody2D` enemies |
| 3 | Projectiles | `Area2D` projectiles |
| 4 | Pickups | `Area2D` XP gems |
| 5 | Obstacles | `StaticBody2D` world obstacles |

- `collision_layer` = which layer(s) this body IS ON (bitmask)
- `collision_mask` = which layer(s) this body COLLIDES WITH (bitmask)

**Player:** layer=1, mask=2|16=18 (collides with enemies + obstacles)
**Enemy:** layer=2, mask=1|16=18 (collides with player + obstacles)
**Projectile:** layer=4, mask=2 (collides with enemies only)
**XP Gem:** layer=8, mask=1 (collides with player only)
**Obstacle:** layer=16, mask=0 (static, doesn't scan for collisions)

**Decimal values:** 1, 2, 4, 8, 16, 32, 64...

### CollisionShape2D and resources

**Rule:** `CollisionShape2D.shape` is a **resource**, not a child node. Set
it via the `shape` property, not by adding a `RectangleShape2D` as a child.

In `.tscn`:
```
[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(28, 28)

[node name="Collision" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")
```

Via the MCP tool (the server coerces the shape resource type):
```
godot_scene_edit_set_node_property(
    node_path='Player/Collision', property='shape',
    value={'type': 'RectangleShape2D', 'size': {'x': 32, 'y': 32}})
```

---

## 5. GDScript 4.7 type inference

### The `:=` type-inference trap

**Rule:** Godot 4.7's GDScript type inference is strict. `var x := expr`
fails to compile when the expression's type can't be statically determined.

**Common breakage:**
```gdscript
var player := get_tree().get_first_node_in_group("player")  # ❌ returns Node
var dir := (player.global_position - pos).normalized()        # ❌ player is untyped
var best := null                                              # ❌ can't infer from null
```

**Fix — explicit type annotations:**
```gdscript
var player: Node2D = get_tree().get_first_node_in_group("player")
var dir: Vector2 = (player.global_position - pos).normalized()
var best: Node2D = null
```

**Also breaks with `load().instantiate()`:**
```gdscript
var main := load("res://scenes/main.tscn").instantiate()  # ❌ untyped
var main: Node = load("res://scenes/main.tscn").instantiate()  # ✅
```

### PackedVector2Array constructor

**Rule:** In GDScript, `PackedVector2Array` takes `Vector2` objects, not
flat floats:
```gdscript
# ❌ Parse error:
poly.polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)

# ✅ Correct:
poly.polygon = PackedVector2Array([
    Vector2(-16, -16), Vector2(16, -16), Vector2(16, 16), Vector2(-16, 16)
])
```

**Exception:** In `.tscn` text format, the flat-float form IS valid:
```
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
```

### Signal list changes are breaking

**Rule:** When you remove or rename a signal on a script that other scripts
connect to, those connections break at runtime with:
```
Invalid access to property or key 'old_signal' on a base object
```

**Do this:** When migrating a signal:
1. Update every script that connects to it in the same change
2. Write a test that pins the signal contract:
```gdscript
func test_old_signal_removed() -> void:
    var sigs := gm.get_signal_list()
    for sig in sigs:
        assert_ne(sig["name"], "old_signal", "old_signal should be removed")
```

---

## 6. Scene file format (.tscn)

### Structure

```
[gd_scene format=3 uid="uid://..."]

[ext_resource type="Script" path="res://scripts/player.gd" id="1_abc"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 32)

[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
collision_layer = 1
script = ExtResource("1_abc")

[node name="Body" type="Polygon2D" parent="Player"]
polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)
color = Color(0.2, 0.8, 1, 1)

[node name="Collision" type="CollisionShape2D" parent="Player"]
shape = SubResource("Rect_1")
```

### Key rules
- `ext_resource` = external file reference (scripts, scenes, textures)
- `sub_resource` = inline resource (shapes, materials, animations)
- Node order in the file = tree order = render order (for 2D)
- `parent="."` = child of root; `parent="Player"` = child of Player
- `groups=["player"]` = the node's groups
- `unique_id` = Godot's internal node ID (auto-generated, don't reuse)

### Editing scenes and scripts

- **Via the MCP tools:** `godot_scene_edit_create_node`, `godot_scene_edit_set_node_property`, `godot_scene_edit_attach_script`, `godot_scene_edit_save_scene` — enable the right toolsets first (see `godot-getting-started`).
- **On disk:** edit the `.tscn`/`.gd` file directly, then reload in the editor (`godot_scene_edit_reload_scene` or Project → Reload Current Project).
- **Saving rules:**
  - **Scripts** (`godot_scripts_write` / `godot_scripts_patch`) flush to disk immediately — no scene save needed. The editor picks the change up on the next script reload.
  - **Scene edits** (create/rename/delete nodes, set properties) live in the editor's memory until you call `godot_scene_edit_save_scene()` (or `godot_scene_edit_save_all_scenes()`). Always save before running headless `godot_runtime_run_and_capture` — it runs the files on disk, not the in-memory scene.

---

## 7. Infinite/background grids

### Dynamic tile pool pattern

For an infinite scrolling background, don't generate tiles for the entire
world. Pre-allocate a pool sized to the viewport and reposition tiles as
the camera moves:

```gdscript
func _ready() -> void:
    _calc_view_radius()
    _init_tile_pool()

func _calc_view_radius() -> void:
    var vp := get_viewport().get_visible_rect().size
    var zoom := Vector2.ONE
    var cam := get_viewport().get_camera_2d()
    if cam:
        zoom = cam.zoom
    _view_radius_x = int(ceil((vp.x / zoom.x) / TILE_SIZE / 2.0)) + 2
    _view_radius_y = int(ceil((vp.y / zoom.y) / TILE_SIZE / 2.0)) + 2

func _process(_delta: float) -> void:
    var cam := _camera_pos()
    var gx := int(floor(cam.x / TILE_SIZE))
    var gy := int(floor(cam.y / TILE_SIZE))
    if gx != _last_grid_x or gy != _last_grid_y:
        _update_tiles(gx, gy)
```

**Key:** Size the pool from the actual viewport, not a hardcoded constant.
A hardcoded `VIEW_RADIUS=12` that works at 1280x720 won't fill 1920x1080.

---

## 8. MCP tool workflow

The bridge between the server and the editor is managed for you — the Godot addon connects to the MCP server's WebSocket listener automatically (enable the plugin once in Project Settings → Plugins). Agents never talk to the bridge directly; call the `godot_<toolset>_<action>` tools.

### Session start (every session)

```
godot_health_check()        # bridge connected? server version
godot_get_server_info()    # toolsets + tool counts, active scene, next_steps
godot_list_toolsets()      # what's enabled / each toolset's min Godot version
godot_enable_toolset('scene_edit')
godot_enable_toolset('scripts')
```

If the bridge is offline: open the `godot/` project in Godot 4.4+ with the addon enabled — the status dock shows the connection state.

### Common tool calls

| Tool | Purpose |
|------|---------|
| `godot_inspection_get_project_info()` | Project name, autoloads, input actions |
| `godot_inspection_get_scene_tree()` | Current scene tree (max_depth) |
| `godot_scene_edit_open_scene()` | Open a scene in the editor |
| `godot_scene_edit_create_node()` | Add a node to the active scene |
| `godot_scene_edit_set_node_property()` | Set a property (handles type coercion) |
| `godot_scene_edit_attach_script()` | Attach a .gd script to a node |
| `godot_scripts_write()` | Write/overwrite a .gd file (flushes to disk) |
| `godot_scene_edit_add_to_group()` | Add a node to a group |
| `godot_scene_edit_save_scene()` | Save the active scene to disk |
| `godot_scene_edit_save_all_scenes()` | Save all open scenes |
| `godot_runtime_play_scene()` | Play the scene in the editor |
| `godot_runtime_run_and_capture()` | Headless run + captured errors/output |
| `godot_scene_edit_close_scene()` | Close a scene tab (destructive, needs confirm) |
| `godot_undo()` | Undo the last editor action (always-on core) |

### Gotchas

- **Scene edits need an explicit save** (`godot_scene_edit_save_scene()`); script writes don't — they hit disk immediately
- Changing `project.godot` on disk requires **Project → Reload Current Project** (or `godot_scene_edit_reload_scene()` for the scene)
- `godot_runtime_run_and_capture()` runs the **files on disk** — save the scene first
- Every mutation is undoable in the editor's undo history; `godot_undo()` steps back one action
- Live inspection/input during play needs the `MCPRuntimeProbe` autoload in the game (see `godot-playtest-and-debug`)

---

## 9. Testing with GUT

### Running GDScript tests

```bash
# Via the MCP tool:
godot_testing_run_tests(test_dir="res://tests/unit")

# Directly:
godot --headless --path examples/survivors -s addons/gut/gut_cmdln.gd -gexit
```

### GUT test patterns

```gdscript
extends GutTest

var _player: CharacterBody2D

func before_each() -> void:
    # Instantiate with the script — don't load the full scene (it may
    # generate a world, spawn enemies, or hang on ready signals).
    _player = CharacterBody2D.new()
    _player.set_script(load("res://scripts/player.gd"))
    add_child(_player)

func after_each() -> void:
    _player.free()

func test_player_starts_with_full_health() -> void:
    assert_eq(_player.health, 100.0, "Starts at 100 HP")
```

### GUT gotchas

- **Don't `await wait_for_signal(node.ready)` on simple nodes** — `_ready`
  fires synchronously on `add_child`. Awaiting can hang the test.
- **Don't instantiate heavy scenes in `before_each`** — a scene with
  world generation or 1600 tiles will hang or time out. Instantiate the
  node + script directly instead.
- **GUT 9.7 omits the "Failing Tests" line** when all tests pass. The
  godot-mcp parser handles this (issue: fixed in `gut_parse.py`).
- **`assert_contains` doesn't exist** in GUT 9.7. Use
  `assert_string_contains(str, substring, msg)`.
- **Autoload state leaks between tests** — reset it in `before_each`:
  `get_node("/root/GameManager")._change_state(State.MENU)`.

---

## 10. Quick checklist — before playing a scene

- [ ] Background/Obstacles nodes are BEFORE Player in the scene tree (z-order)
- [ ] Entity visuals are `Polygon2D` (Node2D), not `ColorRect` (Control)
- [ ] Dynamically spawned entities are children of the scene root, not the autoload
- [ ] Full-screen overlay `Control` has `mouse_filter = IGNORE` (2)
- [ ] Custom input actions are in `project.godot` and project was reloaded
- [ ] All scripts parse clean: `godot --headless --check-only --script <path>` or `godot_scripts_get_parse_errors()`
- [ ] GUT tests pass: `godot_testing_run_tests()` or `godot --headless -s addons/gut/gut_cmdln.gd -gexit`
- [ ] Scene saved to disk: `godot_scene_edit_save_scene()` after scene edits (scripts flush on write)

---

## Specialized reference guides

For deeper detail on specific topics, see the reference files:

- **[references/ui-hud.md](references/ui-hud.md)** — CanvasLayer vs Node2D,
  Control layout (anchors, presets, mouse_filter), full-screen overlay
  pattern, the input-blocking trap, ProgressBar/Label/Button patterns
- **[references/physics-collision.md](references/physics-collision.md)** —
  Body types (CharacterBody2D vs Area2D vs StaticBody2D), collision
  layer/mask convention and bitmask values, CollisionShape2D resources,
  contact detection (slide collisions vs body_entered)
- **[references/testing-gut.md](references/testing-gut.md)** — GUT setup and
  install, test patterns (signals, groups, state machines), GUT gotchas
  (no await ready, no assert_contains, autoload state leak), MCP run_tests
- **[references/scene-authoring.md](references/scene-authoring.md)** — .tscn
  format (ext_resource, sub_resource, node blocks), text vs GDScript
  syntax differences, disk vs bridge editing, common scene patterns
- **[references/autoload-architecture.md](references/autoload-architecture.md)**
  — Autoload registration and lifecycle, the autoload-children rendering
  trap, state persistence across reloads, state machine pattern, signal
  contracts, entity group convention
- **[references/scene-templates.md](references/scene-templates.md)** —
  Ready-to-use .tscn templates for player, enemy, projectile, main scene,
  and WASD input actions
- **[references/common-bugs.md](references/common-bugs.md)** — 11 documented
  bugs with symptom/root cause/fix from real development