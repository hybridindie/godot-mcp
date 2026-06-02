"""Typed results for animation tools (issue #39)."""

from __future__ import annotations

from pydantic import BaseModel


class CreateAnimationResult(BaseModel):
    player_path: str
    animation: str
    length: float = 0.0
    dry_run: bool = False


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
