"""Typed results for project scaffold tool (issue #112)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScaffoldProjectResult(BaseModel):
    created: bool = False
    paths_created: list[str] = Field(default_factory=list)
    autoloads_registered: list[str] = Field(default_factory=list)
    dry_run: bool = False
