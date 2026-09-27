"""Typed results for runtime inspection tools (issue #35)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.json_strict import JSONBool, JSONInt, JSONStr


class MonitorResult(BaseModel):
    monitoring: JSONBool
    node_path: JSONStr
    property: JSONStr
    samples: JSONInt = 0
    # #536 push-on-change sampling: only changed values are queued (default);
    # epsilon is the float-comparison tolerance for the change test.
    on_change_only: JSONBool = True
    epsilon: float = 0.0001


class PropertySample(BaseModel):
    frame: JSONInt
    value: Any = None


class PropertySamplesResult(BaseModel):
    ready: JSONBool = False
    connected: JSONBool = False
    node_path: JSONStr = ""
    property: JSONStr = ""
    samples: list[PropertySample] = Field(default_factory=list)
    error: JSONStr = ""
    # #459: stable reason token while pending (capture_pending).
    reason: str | None = None


class ReadPropertyResult(BaseModel):
    """One-shot live property read (#571): the value now, from the probe's
    dedicated read path that never touches the monitor slot."""

    ready: JSONBool = False
    node_path: JSONStr = ""
    property: JSONStr = ""
    value: Any = None
    error: JSONStr = ""
    # #459: stable reason token while pending (read_pending).
    reason: str | None = None


class Rect(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class UiElement(BaseModel):
    path: JSONStr
    name: JSONStr
    node_class: JSONStr = ""
    visible: JSONBool = False
    rect: Rect = Field(default_factory=Rect)
    text: JSONStr = ""


class UiElementsResult(BaseModel):
    ready: JSONBool = False
    elements: list[UiElement] = Field(default_factory=list)
    # #459: stable reason token while pending (scan_in_flight).
    reason: str | None = None
