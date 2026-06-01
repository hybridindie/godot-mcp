"""Unit tests for the tower-defense domain model (issue #7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.models.domain import (
    DomainVocabulary,
    Economy,
    Enemy,
    EnemyArchetype,
    MetaProgression,
    Path,
    RunState,
    Tower,
    TowerArchetype,
    Wave,
    WaveModifier,
)


def test_tower_construction_and_defaults() -> None:
    tower = Tower(
        id="archer_basic",
        name="Archer",
        archetype=TowerArchetype.ARCHER,
        damage=10.0,
        range=200.0,
        fire_rate=1.5,
        cost=50,
    )
    assert tower.placement.value == "ground"  # default
    assert tower.upgrades == []
    assert tower.scene_path is None


def test_tower_with_upgrades_and_scene() -> None:
    tower = Tower.model_validate(
        {
            "id": "cannon",
            "name": "Cannon",
            "archetype": "cannon",
            "damage": 40,
            "range": 150,
            "fire_rate": 0.5,
            "cost": 120,
            "placement": "elevated",
            "scene_path": "res://towers/cannon.tscn",
            "upgrades": [{"tier": 1, "cost": 80, "damage": 60}],
        }
    )
    assert tower.archetype is TowerArchetype.CANNON
    assert tower.upgrades[0].damage == 60


def test_enemy_defaults() -> None:
    enemy = Enemy(
        id="grunt", name="Grunt", archetype=EnemyArchetype.BASIC, hp=30, speed=80, reward=5
    )
    assert enemy.armor == 0.0
    assert enemy.path_behavior == "follow_path"


def test_wave_with_modifier_and_groups() -> None:
    wave = Wave.model_validate(
        {
            "number": 3,
            "modifier": "double_speed",
            "spawn_groups": [{"enemy_type": "grunt", "count": 10, "interval": 0.5}],
            "total_reward": 60,
        }
    )
    assert wave.modifier is WaveModifier.DOUBLE_SPEED
    assert wave.spawn_groups[0].count == 10


def test_path_waypoints() -> None:
    path = Path.model_validate({"id": "main", "waypoints": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]})
    assert len(path.waypoints) == 2
    assert path.waypoints[1].x == 100.0


def test_economy_and_meta_defaults() -> None:
    economy = Economy(starting_gold=100, lives=20)
    assert economy.gold_per_wave == 0
    assert economy.upgrade_cost_table == {}

    meta = MetaProgression(run_seed=42)
    assert meta.run_state is RunState.IN_PROGRESS
    assert meta.unlocked_towers == []


def test_invalid_archetype_rejected() -> None:
    with pytest.raises(ValidationError):
        Tower(
            id="x",
            name="X",
            archetype="laser",  # type: ignore[arg-type]
            damage=1,
            range=1,
            fire_rate=1,
            cost=1,
        )


def test_vocabulary_lists_all_archetypes() -> None:
    vocab = DomainVocabulary.current()
    assert vocab.tower_archetypes == ["archer", "cannon", "freeze", "aoe", "support"]
    assert "boss" in vocab.enemy_archetypes
    assert "path_adjacent" in vocab.placement_types
