"""Typed results for navigation tools (issue #43)."""

from __future__ import annotations

from pydantic import BaseModel


class NavigationRegionResult(BaseModel):
    node_path: str
    region_type: str
    created: bool = False
    dry_run: bool = False


class NavigationAgentResult(BaseModel):
    node_path: str
    agent_type: str
    created: bool = False
    dry_run: bool = False


class BakeNavigationResult(BaseModel):
    node_path: str
    baked: bool = False
    dry_run: bool = False


class NavigationLayersResult(BaseModel):
    node_path: str
    navigation_layers: int = 0
    dry_run: bool = False
