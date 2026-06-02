"""Typed results for project & filesystem tools (issue #32)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FsEntry(BaseModel):
    """A filesystem node: a file, or a directory with children."""

    name: str
    path: str
    type: str  # "file" | "directory"
    children: list[FsEntry] = Field(default_factory=list)


class FilesystemTree(BaseModel):
    tree: FsEntry


class SearchResult(BaseModel):
    matches: list[str] = Field(default_factory=list)
    truncated: bool = False


class SettingValue(BaseModel):
    name: str
    value: Any = None
    exists: bool = False


class SetSettingResult(BaseModel):
    name: str
    value: Any = None
    set: bool = False
    dry_run: bool = False


class UidResolution(BaseModel):
    uid: str | None = None
    path: str | None = None
