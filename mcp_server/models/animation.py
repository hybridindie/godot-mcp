"""Typed results for animation tools (issue #39)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateAnimationResult(BaseModel):
    player_path: str
    animation: str
    length: float = 0.0
    dry_run: bool = False


class AnimationList(BaseModel):
    """The animations on an AnimationPlayer (issue #218)."""

    player_path: str
    animations: list[str] = Field(default_factory=list)


class AnimationKey(BaseModel):
    """One keyframe: ``time`` and its JSON-coerced ``value``."""

    time: float
    value: Any = None


class AnimationTrack(BaseModel):
    type: str
    path: str
    keys: list[AnimationKey] = Field(default_factory=list)


class AnimationDetail(BaseModel):
    """An animation's tracks and keyframes (issue #218) — inverts the animation writers."""

    name: str
    length: float = 0.0
    loop_mode: str = "none"
    tracks: list[AnimationTrack] = Field(default_factory=list)


class AnimationTrackResult(BaseModel):
    animation: str
    track: int = -1
    track_path: str = ""
    dry_run: bool = False


class KeyframeResult(BaseModel):
    animation: str
    track: int
    time: float
    dry_run: bool = False


class AnimationTreeResult(BaseModel):
    node_path: str
    root_type: str
    dry_run: bool = False


class StateMachineStateResult(BaseModel):
    tree_path: str
    state: str
    dry_run: bool = False


class BlendTreeNodeResult(BaseModel):
    tree_path: str
    node: str
    node_type: str
    dry_run: bool = False
