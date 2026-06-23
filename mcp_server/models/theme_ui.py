"""Typed results for theme/UI tools (issue #46)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ThemeResult(BaseModel):
    node_path: str
    theme_path: str = ""
    created: bool = False
    dry_run: bool = False


class ThemeColorResult(BaseModel):
    node_path: str
    name: str
    dry_run: bool = False


class ThemeFontSizeResult(BaseModel):
    node_path: str
    name: str
    size: int = 0
    dry_run: bool = False


class ThemeStyleboxResult(BaseModel):
    node_path: str
    name: str
    stylebox_type: str
    dry_run: bool = False


class StyleBoxOverride(BaseModel):
    """One stylebox override (issue #219 G7): its name, StyleBox ``type``, and the
    serialized ``properties`` — enough to recreate it via ``set_theme_stylebox``."""

    name: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class NodeThemeOverrides(BaseModel):
    """A Control's per-node theme overrides (issue #219 G7) — the inverse of
    ``set_theme_color`` / ``set_theme_font_size`` / ``set_theme_stylebox``. ``colors``
    map override name → ``{r,g,b,a}``; ``font_sizes`` map name → int."""

    node_path: str
    colors: dict[str, Any] = Field(default_factory=dict)
    font_sizes: dict[str, int] = Field(default_factory=dict)
    styleboxes: list[StyleBoxOverride] = Field(default_factory=list)
