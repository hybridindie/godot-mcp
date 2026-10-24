"""Typed results for project validation (#758)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from mcp_server.models.envelope import NextCall


class ValidationFinding(BaseModel):
    """One validator finding. ``severity="error"`` makes the run invalid."""

    validator: str | None = None
    severity: Literal["error", "warning", "info"] = "error"
    path: str | None = None
    message: str
    next_call: NextCall | None = None


class ValidateProjectResult(BaseModel):
    """The project-level validator verdict.

    ``valid`` is false when any finding has severity ``error``. The tool call
    itself succeeded (`ok` is true) — project invalid is a result, not a tool
    failure, so the findings stay inspectable.
    """

    valid: bool = True
    findings: list[ValidationFinding] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    scoped_to: list[str] = Field(default_factory=list)
    project_dir: str | None = None
    hint: str | None = None
