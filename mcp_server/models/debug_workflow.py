"""Debug workflow result model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DebugWorkflowResult(BaseModel):
    """Unified debug report returned by ``debug_workflow``."""

    bridge: dict[str, Any]
    scene_tree: dict[str, Any] | None
    run: dict[str, Any] | None
    parse: dict[str, Any]
    findings: list[str]
    suggestions: list[str]
