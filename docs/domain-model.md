# Domain model: tower-defense roguelite

This is the game-specific vocabulary that makes godot-mcp speak *tower defense*
rather than generic Godot. The Pydantic models in
[`mcp_server/models/domain.py`](../mcp_server/models/domain.py) are the source of
truth; this document is their spec. These types drive the semantic tools in
issues #8 (placement) and #9 (waves/paths) and the vertical slice (#15).

> Implemented in issue #7 (MCP-only — no addon work). The `get_domain_vocabulary`
> tool returns the enumerated vocabulary below for agent introspection.

## Naming conventions

- **All data fields are `snake_case`** (`fire_rate`, `starting_gold`, `scene_path`).
- **Enum values are lowercase snake** (`path_adjacent`, `double_speed`, `in_progress`).
- **Identifiers** (`id`) are `snake_case` slugs unique within their type
  (`archer_basic`, `fast_grunt`).
- **Scene/resource references** are Godot `res://` paths in `scene_path` /
  `curve_node_path` fields, or scene-relative node paths (e.g. `Path2D`) where noted.

## Godot mapping

These design-time models describe content the agent then realizes as Godot scenes
and resources through the mutation tools (#6) and the semantic tools (#8/#9):

| Domain type | Godot realization |
|-------------|-------------------|
| `Tower` | a `.tscn` at `scene_path` (root is the tower body; `archetype`/stats drive its script exports) |
| `Enemy` | a `.tscn` at `scene_path` following a path |
| `Path` | a `Path2D` + `Curve2D` (`curve_node_path`); `waypoints` seed the curve; `start_marker`/`end_marker` are `Marker2D` node paths |
| `Wave` | data consumed by a spawner node; `spawn_groups` time enemy instantiation |
| `Economy` | run parameters held by a game-state autoload/resource |
| `MetaProgression` | lightweight run state (seed, unlocks, reward choices, relics) |

`Waypoint {x, y}` maps to a Godot `Vector2` (coerced by `type_coerce.gd`, #5/#6).

## Systems

### Tower
`id, name, archetype, damage, range, fire_rate, cost, placement, upgrades[], scene_path?`
- `archetype`: `archer | cannon | freeze | aoe | support`
- `placement`: `ground | elevated | path_adjacent` (default `ground`)
- `fire_rate` is shots per second.
- `upgrades`: ordered `UpgradeTier { tier, cost, damage?, range?, fire_rate?, description? }`;
  a set stat field overrides the base at that tier.

```json
{
  "id": "cannon_basic",
  "name": "Cannon",
  "archetype": "cannon",
  "damage": 40.0,
  "range": 150.0,
  "fire_rate": 0.5,
  "cost": 120,
  "placement": "elevated",
  "scene_path": "res://towers/cannon.tscn",
  "upgrades": [
    { "tier": 1, "cost": 80, "damage": 60.0, "description": "Reinforced barrel" }
  ]
}
```

### Enemy
`id, name, archetype, hp, speed, reward, armor, path_behavior, scene_path?`
- `archetype`: `basic | fast | armored | flying | boss`
- `speed` is units/second along the path; `reward` is gold on kill; `armor` defaults `0`.

```json
{
  "id": "fast_grunt",
  "name": "Fast Grunt",
  "archetype": "fast",
  "hp": 25.0,
  "speed": 140.0,
  "reward": 8,
  "armor": 0.0,
  "scene_path": "res://enemies/fast_grunt.tscn"
}
```

### Wave
`number, spawn_groups[], total_reward, modifier?`
- `SpawnGroup { enemy_type, count, interval }` — `enemy_type` references an `Enemy.id`;
  `interval` is seconds between spawns in the group.
- `modifier`: `shielded | double_speed | regenerating | swarm` (optional).

```json
{
  "number": 3,
  "modifier": "double_speed",
  "total_reward": 60,
  "spawn_groups": [
    { "enemy_type": "fast_grunt", "count": 10, "interval": 0.5 }
  ]
}
```

### Path
`id, waypoints[], curve_node_path?, start_marker?, end_marker?`

```json
{
  "id": "main_path",
  "waypoints": [ { "x": 0.0, "y": 300.0 }, { "x": 512.0, "y": 300.0 } ],
  "curve_node_path": "Path2D",
  "start_marker": "Markers/Start",
  "end_marker": "Markers/End"
}
```

### Economy
`starting_gold, lives, gold_per_wave, upgrade_cost_table`
- `upgrade_cost_table` maps an upgrade key (e.g. `tier_1`) to its gold cost.

```json
{
  "starting_gold": 100,
  "lives": 20,
  "gold_per_wave": 25,
  "upgrade_cost_table": { "tier_1": 80, "tier_2": 160 }
}
```

### Meta progression (roguelite layer)
Deliberately lightweight in v1: a run seed/state plus reward choices, unlocked
towers, and passive modifiers (relics).

`run_seed, run_state, current_wave, unlocked_towers[], reward_choices[], passive_modifiers[]`
- `run_state`: `in_progress | victory | defeat`
- `RewardChoice { id, name, description? }`, `PassiveModifier { id, name, description? }`

```json
{
  "run_seed": 1337,
  "run_state": "in_progress",
  "current_wave": 3,
  "unlocked_towers": ["archer_basic", "cannon_basic"],
  "reward_choices": [ { "id": "relic_sharp", "name": "Sharpened Arrows" } ],
  "passive_modifiers": [ { "id": "relic_sharp", "name": "Sharpened Arrows", "description": "+10% archer damage" } ]
}
```

## Extensibility

Models keep sensible defaults and optional fields so the design can evolve: add an
archetype by extending the `StrEnum`, add a stat by adding an optional field. New
required fields are a breaking change — coordinate with the tools that build these
(#8/#9) and update this doc and the example payloads in the same change.
