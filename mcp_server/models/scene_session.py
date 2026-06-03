"""Typed results for scene session tools (issue #79).

 scene management: open, reload, save-all, list-open, select-nodes.
"""

from __future__ import annotations

from pydantic import BaseModel


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
    modified: bool = False


class ListOpenScenesResult(BaseModel):
    scenes: list[OpenSceneInfo] = []


class SelectNodesResult(BaseModel):
    scene_path: str
    selected: list[str] = []
    count: int = 0
    dry_run: bool = False
