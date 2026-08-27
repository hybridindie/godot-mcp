"""Typed result for the safety-class introspection tool (issue #366)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SafetyClassListing(BaseModel):
    """Result of ``list_tools_by_safety_class`` — tool names grouped by safety class."""

    tools_by_safety_class: dict[str, list[str]] = Field(
        description="Tool names keyed by safety_class (read_only / mutating / "
        "destructive / runtime); unclassified tools (if any) appear under "
        "'unclassified'."
    )