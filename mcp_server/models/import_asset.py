"""Typed results for asset import tools (issue #108)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportAssetResult(BaseModel):
    imported: bool = False
    target_path: str
    detected_type: str | None = None
    dry_run: bool = False
    scan_complete: bool = False


class CreateMaterialResult(BaseModel):
    material_path: str
    created: bool = False
    channels_set: list[str] = Field(default_factory=list)
    dry_run: bool = False


class ImportStatusResult(BaseModel):
    imported: bool = False
    last_modified: str | None = None
    type: str | None = None
    # #459/#453: true while the editor's filesystem scan is in flight — a status
    # read then is provisional (an import just triggered the scan).
    scanning: bool = False
    # Stable reason token while pending: ``rescan_in_flight`` when not yet
    # imported and the scan is running.
    reason: str | None = None
