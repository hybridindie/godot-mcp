# Autoload & Game Architecture

## Autoloads

### What they are

An autoload is a singleton — a script that Godot instantiates once at
startup and keeps alive for the entire game session. Access it by name
from anywhere:

```gdscript
var gm := get_node_or_null("/root/GameManager")
```

### Registering

In `project.godot`:
```ini
[autoload]
GameManager="*res://scripts/game_manager.gd"
```

The `*` prefix means "instantiate this script as a node." Without `*`,
Godot loads the script but doesn't instantiate it.

### When to use autoloads

- Game manager (state machine, score, wave logic)
- Audio manager (global bus control)
- Scene transition manager
- Event bus (global signal hub)

### When NOT to use autoloads

- Don't use as a dumping ground for unrelated globals
- Don't store per-scene state (it persists across reloads)
- Don't add visual children to a non-Node2D autoload (see below)

---

## The autoload-children rendering trap

**The #1 architecture bug:** An autoload that is `extends Node` (not
`Node2D`) spawns entities via `add_child(enemy)`. The enemy's `Polygon2D`
body is invisible — it exists in the tree but has no 2D world transform.

**Root cause:** `Polygon2D`, `Sprite2D`, and other `Node2D` visual nodes
only render inside a `Node2D`/`CanvasItem` subtree. A plain `Node`
autoload provides no 2D world context.

**Fix — spawn into the scene root:**
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
    world.add_child(enemy)        # ← scene root, not autoload
    enemy.global_position = pos
```

**Don't do this:**
- ❌ `add_child(enemy)` on a `Node` autoload
- ❌ `get_tree().root.add_child(enemy)` — root is a `Window`, not `Node2D`
- ❌ Making the autoload `extends Node2D` — autoloads attach to `/root`,
  which is a `Window`, and `Node2D` under `Window` doesn't get a world

---

## State persistence across scene reloads

**Rule:** Autoload singletons persist across `get_tree().reload_current_scene()`.
Their variables, timers, and signal connections are NOT reset.

**Symptom:** After death + retry, the old score/wave persists, or leftover
enemies are still on screen.

**Fix — explicit reset:**
```gdscript
func start_game() -> void:
    # Clear leftover entities
    for e in get_tree().get_nodes_in_group("enemies"):
        e.queue_free()
    for g in get_tree().get_nodes_in_group("xp_gems"):
        g.queue_free()
    # Reset state
    score = 0
    wave = 1
    spawn_timer = 0.0
    spawn_interval = 2.0
    # Reset player
    var player: Node2D = get_tree().get_first_node_in_group("player")
    if player:
        player.health = 100.0
        player.max_health = 100.0
        player.xp = 0
        player.level = 1
        player.xp_to_next = 5
        player.global_position = Vector2.ZERO
        player.update_ui()
    _change_state(State.PLAYING)
```

---

## State machine pattern

For a game with menu/playing/paused/game-over states:

```gdscript
extends Node

enum State { MENU, PLAYING, PAUSED, GAME_OVER }
var state: State = State.MENU

signal state_changed(state: int)

func _ready() -> void:
    _change_state(State.MENU)

func _unhandled_input(event: InputEvent) -> void:
    if event.is_action_pressed("ui_cancel"):       # ESC
        if state == State.PLAYING:
            _change_state(State.PAUSED)
        elif state == State.PAUSED:
            _change_state(State.PLAYING)
    elif event.is_action_pressed("ui_accept"):     # SPACE/Enter
        if state == State.MENU or state == State.GAME_OVER:
            start_game()

func _change_state(new_state: State) -> void:
    state = new_state
    match state:
        State.MENU:     get_tree().paused = false
        State.PLAYING:  get_tree().paused = false
        State.PAUSED:   get_tree().paused = true
        State.GAME_OVER: get_tree().paused = true
    state_changed.emit(state)
```

### Pause and process_mode

`get_tree().paused = true` freezes all nodes with
`process_mode = PROCESS_MODE_INHERIT` (the default). To keep UI
responsive while paused:

```gdscript
# On the overlay script:
func _ready() -> void:
    process_mode = Node.PROCESS_MODE_ALWAYS
```

For `_unhandled_input` to fire while paused on an autoload, the autoload
also needs `PROCESS_MODE_ALWAYS`. But `_unhandled_input` on autoloads
fires even when paused by default (input processing is separate from
physics processing).

---

## Signal contracts

### When signals change, update every connection

**Bug:** Removing a signal breaks every script that connects to it:
```
Invalid access to property or key 'game_over' on a base object
of type 'Node (game_manager.gd)'
```

**Rule:** When removing/renaming a signal, grep every script for
`.connect` to the old name and update them all in the same pass.

### Test the contract

```gdscript
func test_old_signal_removed() -> void:
    var sigs := _gm.get_signal_list()
    for sig in sigs:
        assert_ne(sig["name"], "game_over",
            "game_over signal should be removed; use state_changed")
```

---

## Entity group convention

Use groups for runtime entity discovery — cheaper and more flexible than
type-checking:

| Group | Who's in it | Who queries it |
|-------|-------------|----------------|
| `"player"` | The player CharacterBody2D | Enemies, gems, HUD, GameManager |
| `"enemies"` | All enemy CharacterBody2D | Projectiles, GameManager, player |
| `"xp_gems"` | All XP gem Area2D | GameManager (cleanup on restart) |

**Find by group:**
```gdscript
var player: Node2D = get_tree().get_first_node_in_group("player")
var enemies: Array = get_tree().get_nodes_in_group("enemies")
```

**Add to group:**
```gdscript
func _ready() -> void:
    add_to_group("enemies")
```

**Don't type-check:** `if body is CharacterBody2D` matches the player too.
Use `if body.is_in_group("enemies")` instead.