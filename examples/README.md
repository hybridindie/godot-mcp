# godot-mcp Examples

Godot projects that demonstrate and test the MCP toolset.

## survivors/

A from-scratch survivors-style game built entirely through the MCP tools — geometry and color only, no external assets. Used as a live testbed for the scene-edit, scripts, physics, and testing toolsets.

### Game features

- **Player**: blue square, WASD/arrows movement, health/XP/leveling, contact damage cooldown
- **Enemies**: red squares, chase AI, health/damage scale per wave, spawn around the player
- **Projectiles**: yellow bars, auto-fire at nearest enemy every 0.5s, lifetime expiry
- **XP gems**: green squares, drop on enemy death, magnet-pickup within 80px
- **World**: 40x40 checkerboard tile grid + 40 deterministic scattered obstacles (StaticBody2D)
- **HUD**: health bar, XP bar, score, wave counter
- **Game loop**: start menu (SPACE/click) → playing → ESC pauses → death → game over with retry

### Project structure

```
examples/survivors/
├── project.godot              # main_scene + GameManager autoload + WASD input actions
├── addons/
│   ├── godot_mcp/             # the MCP addon (editor bridge)
│   └── gut/                   # GUT (Godot Unit Test) for GDScript testing
├── scenes/
│   ├── main.tscn              # Node2D root: Player + HUD + Background + Obstacles
│   ├── enemy.tscn             # CharacterBody2D: red square + chase AI
│   ├── projectile.tscn        # Area2D: yellow bar + collision
│   └── xp_gem.tscn            # Area2D: green square + magnet pickup
├── scripts/
│   ├── player.gd              # movement, health, XP, leveling, collision damage
│   ├── enemy.gd               # chase AI, health, death signal
│   ├── projectile.gd          # direction, lifetime, enemy hit
│   ├── xp_gem.gd              # magnet pickup, XP grant
│   ├── game_manager.gd        # autoload: spawner, waves, auto-shoot, state machine
│   ├── hud.gd                 # health/XP bars, score/wave labels
│   ├── game_over.gd           # start/pause/game-over overlay + restart
│   └── world.gd               # background grid + obstacle generation
└── tests/unit/
    ├── test_player.gd         # 10 tests: health, damage, XP, leveling, signals
    ├── test_enemy.gd          # 6 tests: group, health, damage, death signal
    ├── test_game_manager.gd   # 8 tests: state machine, resets, signal contracts
    ├── test_projectile.gd     # 10 tests: launch, rotation, lifetime, hit logic
    ├── test_xp_gem.gd         # 6 tests: group, pickup, XP grant, double-pickup
    ├── test_world.gd          # 10 tests: tiles, obstacles, determinism, spawn clearance
    └── test_game_over.gd      # 8 tests: overlay visibility, button actions, state sync
```

### Running the GUT test suite

```bash
# Via the MCP tool (from an agent or the in-process client):
godot_testing_run_tests(test_dir="res://tests/unit")

# Directly with the Godot binary:
/Applications/Godot.app/Contents/MacOS/Godot --headless --path examples/survivors \
  -s addons/gut/gut_cmdln.gd -gexit
```

57 tests across 7 files. The MCP `run_tests` tool detects GUT automatically (`framework_absent=true` when not installed).

## vampire/

The original Vampire Survivors demo — a complete game for comprehensive MCP toolset testing. See [`vampire/README.md`](vampire/README.md) for details.