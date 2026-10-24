"""VCS snapshot/restore results (#760)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VcsSnapshotResult(BaseModel):
    snapshot_id: str | None = None
    label: str | None = None
    ref: str | None = None
    commit: str | None = None
    files_snapshotted: int = 0
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "none"


class VcsRestoreResult(BaseModel):
    snapshot_id: str
    label: str | None = None
    restored: bool = False
    files_restored: int = 0
    extra_files: int = Field(
        default=0,
        description="Files created after the snapshot; left in place by restore.",
    )
    dry_run: bool = False
    hint: str | None = None
    reversible_by: Literal["undo", "vcs", "none"] = "none"
