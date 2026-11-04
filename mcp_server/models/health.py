"""Health-check model (issue #4)."""

from __future__ import annotations

from pydantic import BaseModel

from mcp_server.godot_support import GodotSupportInfo


class HealthStatus(BaseModel):
    """Server status and Godot bridge connection state."""

    server: str
    version: str
    transport: str
    bridge_url: str
    bridge_connected: bool
    # The engine actually attached (from the peer hello), and how it relates to
    # the support surface. None/"disconnected" when no editor is connected.
    godot_version: str | None = None
    godot_support: GodotSupportInfo | None = None
    # The connected addon's version (from the handshake, #530) and a hint when it
    # differs from the server's (#629). Both None when no addon is connected or it
    # predates the handshake.
    addon_version: str | None = None
    version_notice: str | None = None
    # #655: set when the bridge listener could not bind its port (e.g. another
    # server owns it) — the cause of a permanently-disconnected bridge, surfaced
    # instead of leaving the agent to guess.
    bridge_bind_error: str | None = None
    # #762 readiness: ready/importing/modal/busy/stale/disconnected/unknown, and
    # milliseconds since the addon's last heartbeat (None before the first).
    editor_status: str | None = None
    editor_heartbeat_age_ms: int | None = None
