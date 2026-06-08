# Vampire Survivors Demo for godot-mcp

A complete Vampire Survivors-style game for comprehensive MCP toolset testing.

## Game Features

- **Player Character**: WASD movement, health bar, XP bar, leveling system
- **Combat**: Projectile shooting + area-of-effect weapon
- **Enemies**: Chase AI with health bars, difficulty scaling by wave
- **XP System**: Gems dropped on enemy death, magnet pickup, leveling with upgrade menu
- **UI**: Health/XP bars, score, wave counter, timer, upgrade menu, game over screen
- **Particles**: Blood burst on enemy death, sparkle on XP pickup
- **Audio**: (Placeholder — can be tested with MCP audio toolset)
- **TileMap**: Grass tile background (placeholder asset)

## MCP Toolset Coverage

| Feature | Toolset(s) Tested |
|---------|-------------------|
| Player character body + sprite | `scene_edit`, `physics` |
| Enemy spawning + AI movement | `scene_edit`, `physics` |
| Projectile spawning | `scene_edit`, `physics` |
| Area weapon hitbox | `scene_edit`, `physics` |
| XP gem pickup + magnet area | `scene_edit`, `physics` |
| Health/XP bars (ProgressBar) | `theme_ui` |
| Upgrade menu (VBoxContainer + Button) | `theme_ui`, `scene_edit` |
| Particle systems (GPUParticles2D) | `particles` |
| Camera2D + follow script | `scene_edit`, `scripts` |
| TileMapLayer for background | `tilemap` |
| Game manager autoload pattern | `scripts`, `scene_edit` |
| Enemy spawner script | `scripts` |
| Signal connections | `scene_edit` |
| Collision layers/masks | `physics` |
| Pause/unpause via `get_tree().paused` | `runtime`, `scripts` |

## Controls

- **WASD / Arrow Keys**: Move player
- **Enemy contact**: Player takes damage
- **Projectiles**: Auto-fire at nearest enemy
- **Area weapon**: Pulses damage around player every second
- **Level up**: Choose upgrade from menu (pauses game)
- **Death**: Shows score, wave, and time; click Restart

## Project Structure

```
examples/vampire/
├── project.godot           # Project config with GameManager autoload
├── scenes/
│   ├── main.tscn           # Main game scene with all systems
│   ├── enemy.tscn          # Enemy template (PackedScene)
│   ├── xp_gem.tscn         # XP gem template (PackedScene)
│   └── tileset.tres        # TileSet resource for background
├── scripts/
│   ├── player.gd           # Player movement, health, XP, upgrades
│   ├── enemy.gd             # Enemy chase AI, health, death
│   ├── enemy_spawner.gd     # Wave-based spawner with difficulty scaling
│   ├── weapon_projectile.gd # Auto-target projectile system
│   ├── weapon_area.gd       # AOE damage pulse weapon
│   ├── xp_gem.gd            # Magnet pickup XP gems
│   ├── game_manager.gd      # Score, wave, time, game over, pause
│   ├── hud.gd               # Health/XP/score/wave/timer UI updates
│   ├── upgrade_menu.gd      # Level-up menu with random options
│   ├── camera_follow.gd     # Smooth follow camera
│   └── game_over_screen.gd  # Restart button handler
└── assets/
    └── (placeholder for textures/sprites)
```

## Testing with MCP

To test this demo with godot-mcp:

1. Open the `examples/vampire/` folder as a Godot project
2. Enable the `godot_mcp` addon in Project Settings > Plugins
3. Connect your MCP client (Claude Code, OpenCode, etc.)
4. Try commands like: "Show me the scene tree", "Create an enemy", "Set player speed to 300",
   "Add a particle effect to the player", "Change the tilemap background color"

## Notes

- Uses placeholder `ColorRect` sprites for quick visual prototyping.
- No external assets required — pure Godot primitives.
- Enemy spawner keeps enemies ≤ 200 to avoid performance issues.
- Game pauses during upgrade menu; unpause after selection.
