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
