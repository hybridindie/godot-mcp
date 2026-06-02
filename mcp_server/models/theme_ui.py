"""Typed results for theme/UI tools (issue #46)."""

from __future__ import annotations

from pydantic import BaseModel


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
