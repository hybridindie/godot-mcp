"""Typed results for scene session tools (issue #79).

 scene management: open, reload, save-all, list-open, select-nodes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpenSceneResult(BaseModel):
    scene_path: str
    opened: bool
    already_open: bool = False
    dry_run: bool = False


class ReloadSceneResult(BaseModel):
    scene_path: str
    reloaded: bool
    dry_run: bool = False


class SaveAllScenesResult(BaseModel):
    saved: bool
    count: int = 0
    dry_run: bool = False


class OpenSceneInfo(BaseModel):
    path: str


class ListOpenScenesResult(BaseModel):
    scenes: list[OpenSceneInfo] = Field(default_factory=list)


class SelectNodesResult(BaseModel):
    scene_path: str
    selected: list[str] = Field(default_factory=list)
    count: int = 0
    dry_run: bool = False


class CloseSceneResult(BaseModel):
    scene_path: str
    closed: bool
    dry_run: bool = False
