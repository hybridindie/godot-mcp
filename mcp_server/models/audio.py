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


class AudioBusRemoveResult(BaseModel):
    """Result of removing an audio bus (issue #219 G8) — the inverse of ``add_audio_bus``.
    Removal is undoable in the editor (the bus + its effects are restored on undo)."""

    name: str
    index: int
    removed: bool = False
    dry_run: bool = False


class AudioBusEffectRemoveResult(BaseModel):
    """Result of removing one effect from an audio bus (issue #219 G8) — the inverse of
    ``add_audio_bus_effect``. Undoable (the effect is re-inserted at its index on undo)."""

    bus: str
    bus_index: int
    effect_index: int
    removed: bool = False
    dry_run: bool = False
