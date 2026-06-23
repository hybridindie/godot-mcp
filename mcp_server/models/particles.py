"""Typed results for particle tools (issue #42)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateParticlesResult(BaseModel):
    node_path: str
    particles_type: str
    created: bool = False
    dry_run: bool = False


class ParticleMaterialResult(BaseModel):
    node_path: str
    properties: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class ParticleGradientResult(BaseModel):
    node_path: str
    stops: int = 0
    dry_run: bool = False


class ParticlePresetResult(BaseModel):
    node_path: str
    preset: str
    dry_run: bool = False


class ParticleColorRamp(BaseModel):
    """A color ramp's gradient stops (issue #219 P4): parallel ``colors`` ({r,g,b,a})
    and ``offsets`` (0..1). Round-trips into ``set_particle_color_gradient``."""

    colors: list[dict[str, float]] = Field(default_factory=list)
    offsets: list[float] = Field(default_factory=list)


class ParticleMaterialDetail(BaseModel):
    """A read of a GPUParticles node's ParticleProcessMaterial (issue #219 P4) — the
    inverse of ``set_particle_material`` / ``set_particle_color_gradient``. ``properties``
    are JSON-coerced material fields; ``color_ramp`` is the gradient (null when none)."""

    node_path: str
    has_material: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    color_ramp: ParticleColorRamp | None = None
