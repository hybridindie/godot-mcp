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


class GameOutputEntry(BaseModel):
    """One captured line from the running game's output stream (issue #534)."""

    seq: int
    kind: str  # "stdout" | "error" | "warning"
    text: str
    time_ms: float = 0.0


class GameOutputResult(BaseModel):
    """The running game's captured output ring (issue #534).

    ``since_seq`` filtering is applied by the addon: entries carry a monotonic
    ``seq`` cursor so a poll loop can pull incrementally. Honesty counts:
    ``dropped`` is the number of entries evicted by the bounded ring (never
    silent), ``total`` the count ever captured.
    """

    playing: bool
    connected: bool
    entries: list[GameOutputEntry] = Field(default_factory=list)
    next_seq: int = 0
    total: int = 0
    dropped: int = 0
    ready: bool = True
    reason: str = ""
