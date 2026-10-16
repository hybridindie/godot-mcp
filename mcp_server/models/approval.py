"""Human-in-the-loop approval models (issue #153).

The MCP server can POST an :class:`ApprovalRequest` to a configured webhook
before running a destructive tool; the webhook replies with an
:class:`ApprovalResponse`. Both are versioned JSON, like every other boundary.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    """Payload POSTed to the approval webhook before a gated action runs."""

    action: str  # the exposed tool name, e.g. "godot_scene_edit_delete_node"
    safety_class: str  # "destructive" | "mutating" | "runtime"
    params: dict[str, Any] = Field(default_factory=dict)
    task_context: str | None = None
    timestamp: float = 0.0


class ApprovalResponse(BaseModel):
    """The webhook's verdict. Absent/invalid fields default to NOT approved, so a
    malformed reply fails safe rather than silently allowing the action.
    """

    approved: bool = False
    reason: str | None = None
