"""Typed results for project-registered tools (#761)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProjectToolInfo(BaseModel):
    """One project tool that was registered under the ``project`` toolset."""

    name: str
    script: str
    function: str
    safety_class: Literal["read_only", "mutating", "destructive"] = "mutating"
    description: str = ""


class ProjectToolRejection(BaseModel):
    """An annotated function the scanner refused to register."""

    script: str
    function: str | None = None
    reason: str
    line: int | None = None


class ProjectToolsResult(BaseModel):
    """Outcome of a project-tool scan.

    ``rejected`` is honest partial success: a bad annotation never hides the
    tools that did register, and never fails the call.
    """

    registered: list[ProjectToolInfo] = Field(default_factory=list)
    rejected: list[ProjectToolRejection] = Field(default_factory=list)
    count: int = 0

    @model_validator(mode="after")
    def _count_registered(self) -> ProjectToolsResult:
        self.count = len(self.registered)
        return self
