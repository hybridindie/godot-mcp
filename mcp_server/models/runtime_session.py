"""Typed results for the runtime session bridge (issue #66)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlayResult(BaseModel):
    playing: bool
    scene: str = ""
    # True when the play session is paused at a debugger breakpoint (issue
    # #411) — distinguishes "frozen in the debug loop" from "game logic running".
    paused: bool = False


class GameNode(BaseModel):
    """A node in the *running* game's live scene tree (from the runtime probe)."""

    name: str
    type: str
    path: str = ""
    children: list[GameNode] = Field(default_factory=list)


class GameSceneTreeResult(BaseModel):
    playing: bool
    connected: bool = False
    tree: GameNode | None = None
    hint: str = ""
