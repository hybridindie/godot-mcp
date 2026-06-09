"""Typed results for asset import tools (issue #108)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportAssetResult(BaseModel):
    imported: bool = False
    target_path: str
    detected_type: str | None = None
    dry_run: bool = False


class CreateMaterialResult(BaseModel):
    material_path: str
    created: bool = False
    channels_set: list[str] = Field(default_factory=list)
    dry_run: bool = False


class ImportStatusResult(BaseModel):
    imported: bool = False
    last_modified: str | None = None
    type: str | None = None
