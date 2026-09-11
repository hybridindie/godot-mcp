"""Typed results for physics tools (issue #41)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.persistence import PersistenceReport


class SetupBodyResult(PersistenceReport):
    node_path: str
    properties: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class CollisionShapeResult(BaseModel):
    node_path: str
    shape_type: str
    created: bool = False
    dry_run: bool = False


class PhysicsLayersResult(PersistenceReport):
    node_path: str
    collision_layer: int = 0
    collision_mask: int = 0
    dry_run: bool = False


class RaycastResult(BaseModel):
    node_path: str
    created: bool = False
    dry_run: bool = False
