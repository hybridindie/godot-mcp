"""Typed results for runtime inspection tools (issue #35)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MonitorResult(BaseModel):
    monitoring: bool
    node_path: str
    property: str
    samples: int = 0


class PropertySample(BaseModel):
    frame: int
    value: Any = None


class PropertySamplesResult(BaseModel):
    ready: bool = False
    connected: bool = False
    node_path: str = ""
    property: str = ""
    samples: list[PropertySample] = Field(default_factory=list)
    error: str = ""


class Rect(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class UiElement(BaseModel):
    path: str
    name: str
    node_class: str = ""
    visible: bool = False
    rect: Rect = Field(default_factory=Rect)
    text: str = ""


class UiElementsResult(BaseModel):
    ready: bool = False
    elements: list[UiElement] = Field(default_factory=list)
