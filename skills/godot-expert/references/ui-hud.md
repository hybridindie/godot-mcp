# UI & HUD Construction

## CanvasLayer vs Node2D

**Rule:** HUD and UI elements live in a `CanvasLayer` — they render in screen
space and don't move with the world camera. Game entities live under `Node2D`
and render in 2D world space.

```
main (Node2D)
├── Player (CharacterBody2D)     ← world space
└── HUD (CanvasLayer)           ← screen space, always on top
    ├── HealthBar (ProgressBar)
    └── GameOverScreen (Control)
```

**Don't mix:** A `ProgressBar` as a child of a `CharacterBody2D` renders in
world space and won't stay fixed on screen.

---

## Control layout fundamentals

### Anchors and presets

`anchors_preset` is a Godot constant that sets anchor points for common
layouts:

| Value | Name | Use |
|-------|------|-----|
| 0 | TOP_LEFT | Default, no anchoring |
| 1 | TOP_RIGHT | Pin to top-right |
| 8 | CENTER | Center of the screen |
| 15 | FULL_RECT | Fill the entire screen |

For a full-screen overlay:
```
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
```

For a centered container:
```
anchors_preset = 8
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -150.0
offset_top = -80.0
offset_right = 150.0
offset_bottom = 80.0
```

### The zero-size trap

**Bug:** A `Control` is `visible = true` but nothing renders.

**Cause:** `offset_left` and `offset_right` are equal (zero width) or the
node has no anchors and zero size.

**Fix:** Give the node explicit dimensions via offsets or anchors. A
`VBoxContainer` needs non-zero width to lay out children:
```
offset_left = -150.0    # 300px wide centered
offset_right = 150.0
```

---

## mouse_filter — the input-blocking trap

**The #1 UI bug:** A full-screen overlay blocks all keyboard/mouse input,
making the game appear frozen.

| Value | Name | Behavior |
|-------|------|----------|
| 0 | STOP | Receives input, blocks propagation (default for Control) |
| 1 | PASS | Receives input, lets it pass through |
| 2 | IGNORE | Doesn't receive input, lets it pass through |

**Rule:** Set `mouse_filter = 2` (IGNORE) on any Control/ColorRect that
covers the screen as a visual backdrop but shouldn't intercept input:

```gdscript
func _ready() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
```

In `.tscn`:
```
mouse_filter = 2
```

**Keep `mouse_filter` as STOP (0, default) on Buttons** — they need to
receive clicks.

---

## ProgressBar

For health/XP bars:
```gdscript
func _on_health_changed(hp: float, max_hp: float) -> void:
    health_bar.value = (hp / max_hp) * 100.0
```

Set `min_value = 0`, `max_value = 100` (default). The bar fills
proportionally.

In `.tscn`:
```
[node name="HealthBar" type="ProgressBar"]
offset_left = 20.0
offset_top = 20.0
offset_right = 220.0
offset_bottom = 47.0
value = 100.0
```

---

## Full-screen overlay pattern (start/pause/game-over)

```
GameOverScreen (Control, mouse_filter=2, anchors_preset=15)
├── BG (ColorRect, mouse_filter=2, anchors_preset=15, color=black/0.7 alpha)
└── VB (VBoxContainer, anchors_preset=8, centered)
    ├── Label (horizontal_alignment=1)
    └── Button (size_flags_horizontal=4)
```

**State-driven visibility:**
```gdscript
func _on_state_changed(new_state: int) -> void:
    match new_state:
        0: _show("SURVIVORS", "Press SPACE", "Start")
        1: _hide()                    # playing
        2: _show("PAUSED", "", "Resume")
        3: _show("GAME OVER", score, "Retry")
```

**Critical:** In `_ready()`, sync to the current state — the signal may
have fired before the overlay connected:
```gdscript
func _ready() -> void:
    gm.state_changed.connect(_on_state_changed)
    _on_state_changed(gm.state)  # sync now
```

---

## Signal wiring for HUD

The HUD connects to both the player and the GameManager:

```gdscript
func _ready() -> void:
    var player: Node2D = get_tree().get_first_node_in_group("player")
    if player:
        player.health_changed.connect(_on_health_changed)
        player.xp_changed.connect(_on_xp_changed)
    var gm := get_node_or_null("/root/GameManager")
    if gm:
        gm.score_changed.connect(_on_score_changed)
        gm.wave_changed.connect(_on_wave_changed)
```

**Don't connect to signals that were removed/renamed** — it crashes at
runtime. When changing a signal, update every connection in the same pass.