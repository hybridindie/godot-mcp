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


class DeleteResourceFileResult(BaseModel):
    """Result of deleting a ``res://`` file (issue #217). ``had_uid`` is true when a
    ``.uid`` sidecar was removed alongside it. ``tab_closed`` is true when the deleted
    file was a scene open in the editor and its (stale) tab was closed (#422)."""

    path: str
    deleted: bool = False
    had_uid: bool = False
    tab_closed: bool = False
    dry_run: bool = False


class MovedRef(BaseModel):
    """One referencing file the mover rewrote (issue #532), with the number of
    references updated inside it."""

    file: str
    count: int = 0


class MoveResourceFileResult(BaseModel):
    """Result of moving/renaming a ``res://`` file (issue #532).

    ``updated_refs`` lists each file whose references were rewritten. A file move
    is NOT UndoRedo-tracked (``undoable=False`` always, with a recovery hint) —
    reverse it with a second move or version control.
    """

    old_path: str
    new_path: str
    updated_refs: list[MovedRef] = Field(default_factory=list)
    moved: bool = False
    undoable: bool = False
    hint: str | None = None
    dry_run: bool = False
