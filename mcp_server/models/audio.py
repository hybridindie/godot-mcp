"""Typed results for audio tools (issue #44)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AudioPlayerResult(BaseModel):
    node_path: str
    player_type: str
    created: bool = False
    dry_run: bool = False


class AudioBusEffectInfo(BaseModel):
    index: int
    type: str
    enabled: bool = True


class AudioBusInfo(BaseModel):
    index: int
    name: str
    volume_db: float = 0.0
    muted: bool = False
    solo: bool = False
    bypass: bool = False
    effects: list[AudioBusEffectInfo] = Field(default_factory=list)


class AudioBusLayoutResult(BaseModel):
    buses: list[AudioBusInfo] = Field(default_factory=list)


class AudioBusResult(BaseModel):
    index: int
    name: str
    dry_run: bool = False


class AudioBusEffectResult(BaseModel):
    bus: str
    bus_index: int
    effect_type: str
    effect_index: int
    dry_run: bool = False
