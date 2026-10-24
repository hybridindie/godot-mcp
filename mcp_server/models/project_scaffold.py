"""Typed results for project scaffold tool (issue #112)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScaffoldProjectResult(BaseModel):
    created: bool = False
    paths_created: list[str] = Field(default_factory=list)
    autoloads_registered: list[str] = Field(default_factory=list)
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "none"
