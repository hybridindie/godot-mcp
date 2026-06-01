"""Health-check model (issue #4)."""

from __future__ import annotations

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Server status and Godot bridge connection state."""

    server: str
    version: str
    transport: str
    bridge_url: str
    bridge_connected: bool
