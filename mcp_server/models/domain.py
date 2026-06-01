"""Tower-defense roguelite domain model (issue #7).

The game-specific vocabulary that makes this server speak tower-defense rather
than generic Godot. These typed models drive the semantic tools in #8/#9 and the
vertical slice (#15). All fields are ``snake_case``; enum values are lowercase
snake. Models are intentionally permissive (sensible defaults, optional fields)
so the game design can evolve. See ``docs/domain-model.md`` for the full spec,
Godot mapping, and example payloads.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# --- enumerated vocabulary -------------------------------------------------


class TowerArchetype(StrEnum):
    ARCHER = "archer"
    CANNON = "cannon"
    FREEZE = "freeze"
    AOE = "aoe"
    SUPPORT = "support"


class PlacementType(StrEnum):
    GROUND = "ground"
    ELEVATED = "elevated"
    PATH_ADJACENT = "path_adjacent"


class EnemyArchetype(StrEnum):
    BASIC = "basic"
    FAST = "fast"
    ARMORED = "armored"
    FLYING = "flying"
    BOSS = "boss"


class WaveModifier(StrEnum):
    SHIELDED = "shielded"
    DOUBLE_SPEED = "double_speed"
    REGENERATING = "regenerating"
    SWARM = "swarm"


class RunState(StrEnum):
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"


# --- tower -----------------------------------------------------------------


class UpgradeTier(BaseModel):
    """One step in a tower's upgrade path. Stat fields override the base when set."""

    tier: int
    cost: int
    damage: float | None = None
    range: float | None = None
    fire_rate: float | None = None
    description: str | None = None


class Tower(BaseModel):
    """A placeable defensive tower."""

    id: str
    name: str
    archetype: TowerArchetype
    damage: float
    range: float
    fire_rate: float  # shots per second
    cost: int
    placement: PlacementType = PlacementType.GROUND
    upgrades: list[UpgradeTier] = Field(default_factory=list)
    scene_path: str | None = None


# --- enemy -----------------------------------------------------------------


class Enemy(BaseModel):
    """A path-following attacker."""

    id: str
    name: str
    archetype: EnemyArchetype
    hp: float
    speed: float  # units per second along the path
    reward: int  # gold granted on kill
    armor: float = 0.0
    path_behavior: str = "follow_path"
    scene_path: str | None = None


# --- wave ------------------------------------------------------------------


class SpawnGroup(BaseModel):
    """A burst of one enemy type within a wave."""

    enemy_type: str  # references an Enemy.id
    count: int
    interval: float  # seconds between spawns in this group


class Wave(BaseModel):
    """One wave of enemies."""

    number: int
    spawn_groups: list[SpawnGroup] = Field(default_factory=list)
    total_reward: int = 0
    modifier: WaveModifier | None = None


# --- path ------------------------------------------------------------------


class Waypoint(BaseModel):
    """A 2D point on an enemy path (maps to a Godot Vector2)."""

    x: float
    y: float


class Path(BaseModel):
    """An enemy path through the map."""

    id: str
    waypoints: list[Waypoint] = Field(default_factory=list)
    curve_node_path: str | None = None  # a Path2D/Curve2D node in the scene
    start_marker: str | None = None
    end_marker: str | None = None


# --- economy ---------------------------------------------------------------


class Economy(BaseModel):
    """Run-level economy parameters."""

    starting_gold: int
    lives: int
    gold_per_wave: int = 0
    # Maps an upgrade key (e.g. "tier_1") to its gold cost.
    upgrade_cost_table: dict[str, int] = Field(default_factory=dict)


# --- meta progression (roguelite layer) ------------------------------------


class RewardChoice(BaseModel):
    """A choice offered to the player on clearing a wave."""

    id: str
    name: str
    description: str | None = None


class PassiveModifier(BaseModel):
    """A run-long passive effect / relic."""

    id: str
    name: str
    description: str | None = None


class MetaProgression(BaseModel):
    """Lightweight roguelite run state (v1)."""

    run_seed: int
    run_state: RunState = RunState.IN_PROGRESS
    current_wave: int = 0
    unlocked_towers: list[str] = Field(default_factory=list)
    reward_choices: list[RewardChoice] = Field(default_factory=list)
    passive_modifiers: list[PassiveModifier] = Field(default_factory=list)


# --- vocabulary summary (used by the get_domain_vocabulary tool) -----------


class DomainVocabulary(BaseModel):
    """The enumerated vocabulary an agent can use when authoring game content."""

    tower_archetypes: list[str]
    placement_types: list[str]
    enemy_archetypes: list[str]
    wave_modifiers: list[str]
    run_states: list[str]

    @classmethod
    def current(cls) -> DomainVocabulary:
        return cls(
            tower_archetypes=[a.value for a in TowerArchetype],
            placement_types=[p.value for p in PlacementType],
            enemy_archetypes=[a.value for a in EnemyArchetype],
            wave_modifiers=[m.value for m in WaveModifier],
            run_states=[s.value for s in RunState],
        )
