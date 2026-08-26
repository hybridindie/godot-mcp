# Game Physics & Collision

## Body types

| Type | Class | Use case |
|------|-------|----------|
| Static | `StaticBody2D` | Walls, obstacles — don't move, block others |
| Kinematic | `CharacterBody2D` | Player, enemies — moved by code via `move_and_slide()` |
| Area | `Area2D` | Projectiles, pickups, triggers — detect overlap, don't collide |
| Rigid | `RigidBody2D` | Physics-driven objects (rarely needed in survivors-style games) |

### When to use Area2D vs CharacterBody2D

- `CharacterBody2D`: entities that move and collide with the world (player,
  enemies). Use `move_and_slide()` for movement; `get_slide_collision_count()`
  to read contacts.
- `Area2D`: entities that detect overlap but don't physically block
  (projectiles, pickups). Use `body_entered` / `body_exited` signals.
  Connect in `_ready()`:
  ```gdscript
  func _ready() -> void:
      body_entered.connect(_on_body_entered)
  ```

---

## Collision layers & masks

**`collision_layer`** = which layer(s) this body IS ON (bitmask).
**`collision_mask`** = which layer(s) this body SCANS FOR collisions with.

### Convention (survivors game)

| Bit | Decimal | Layer | Who |
|-----|---------|-------|-----|
| 1 | 1 | Player | `CharacterBody2D` player |
| 2 | 2 | Enemies | `CharacterBody2D` enemies |
| 3 | 4 | Projectiles | `Area2D` projectiles |
| 4 | 8 | Pickups | `Area2D` XP gems |
| 5 | 16 | Obstacles | `StaticBody2D` world obstacles |

### Per-entity configuration

| Entity | layer | mask | Rationale |
|--------|-------|------|-----------|
| Player | 1 | 18 (2+16) | Collides with enemies + obstacles |
| Enemy | 2 | 18 (1+16) | Collides with player + obstacles |
| Projectile | 4 | 2 | Overlaps enemies only |
| XP Gem | 8 | 1 | Overlaps player only |
| Obstacle | 16 | 0 | Static — doesn't scan, others scan it |

**Setting via bridge:**
```python
{"command": "cmd_set_node_property",
 "params": {"node_path": "Player", "property": "collision_layer", "value": 1}}
{"command": "cmd_set_node_property",
 "params": {"node_path": "Player", "property": "collision_mask", "value": 18}}
```

**Gotcha:** `collision_layer` and `collision_mask` are on the **physics
body** (CharacterBody2D, Area2D, StaticBody2D), NOT on the
CollisionShape2D child.

---

## CollisionShape2D and shape resources

**Rule:** The `shape` is a **resource**, not a child node. Set it via the
`shape` property using a `SubResource` in `.tscn` or a dict via the bridge.

### In .tscn
```
[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 32)

[node name="Collision" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")
```

### Via the bridge
```python
{"command": "cmd_set_node_property",
 "params": {"node_path": "Player/Collision", "property": "shape",
            "value": {"type": "RectangleShape2D", "size": {"x": 32, "y": 32}}}}
```

### Don't do this
- ❌ Add a `RectangleShape2D` as a child node of `CollisionShape2D`
- ❌ Set `collision_layer` on the `CollisionShape2D` (it's on the body)

---

## Contact detection

### CharacterBody2D (slide collisions)

```gdscript
func _physics_process(delta: float) -> void:
    velocity = input_dir * SPEED
    move_and_slide()
    for i in get_slide_collision_count():
        var col := get_slide_collision(i)
        var collider: Node = col.get_collider()
        if collider and collider.is_in_group("enemies"):
            take_damage(collider.damage)
```

### Area2D (overlap detection)

```gdscript
func _ready() -> void:
    body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
    if body.is_in_group("enemies"):
        body.take_damage(damage)
        queue_free()
```

**Key:** Area2D `body_entered` fires when a **physics body** enters the
area. The body must be on a layer the area's `collision_mask` scans.
Group checks are the reliable way to identify what entered — don't
type-check, use `is_in_group()`.

---

## Type annotations for physics

Godot 4.7 type inference breaks on physics API returns:

```gdscript
# ❌ Parse error:
var collider := col.get_collider()       # returns Object, untyped
var player := get_tree().get_first_node_in_group("player")  # returns Node

# ✅ Explicit types:
var collider: Node = col.get_collider()
var player: Node2D = get_tree().get_first_node_in_group("player")
```