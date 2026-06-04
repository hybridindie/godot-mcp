"""Audio tools (issue #44).

Set up audio over the bridge: stream players, the AudioServer bus layout, and bus
effects. Gated `audio` toolset. ``get_audio_bus_layout`` is `read_only`; the others
are `mutating` (UndoRedo-wrapped addon-side) with `dry_run`.

Note: the bus layout is global editor/AudioServer state, not per-scene — bus and
effect changes apply to the live AudioServer (and are undoable via the editor).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import AUDIO_TAG
from mcp_server.defaults import (
    DEFAULT_AUDIO_BUS_VOLUME_DB,
    DEFAULT_AUDIO_PLAYER_TYPE,
)
from mcp_server.models.audio import (
    AudioBusEffectResult,
    AudioBusLayoutResult,
    AudioBusResult,
    AudioPlayerResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

AUDIO = {AUDIO_TAG}


def register_audio(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the audio tools."""

    @mcp.tool(meta=MUTATING, tags=AUDIO)
    @enforce_preconditions
    async def add_audio_player(
        parent_path: str,
        player_type: str = DEFAULT_AUDIO_PLAYER_TYPE,
        name: str = "",
        stream_path: str = "",
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> AudioPlayerResult:
        """Add an audio player (AudioStreamPlayer / AudioStreamPlayer2D /
        AudioStreamPlayer3D) under ``parent_path``. Optionally load ``stream_path``
        (a ``res://`` AudioStream) and apply ``properties`` (``volume_db``, ``bus``,
        ``autoplay``, ``pitch_scale``).
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return AudioPlayerResult(
                node_path="", player_type=player_type, created=False, dry_run=True
            )
        params = {
            "parent_path": parent_path,
            "player_type": player_type,
            "name": name or player_type,
            "stream_path": stream_path,
            "properties": properties or {},
        }
        return AudioPlayerResult(**await route(bridge, "cmd_add_audio_player", params))

    @mcp.tool(meta=READ_ONLY, tags=AUDIO)
    async def get_audio_bus_layout() -> AudioBusLayoutResult:
        """Return the current AudioServer bus layout: each bus's index, name,
        volume_db, mute/solo/bypass flags, and its effect stack (type + enabled).
        Use this to discover bus names before routing players or adding effects.
        """
        return AudioBusLayoutResult(**await route(bridge, "cmd_get_audio_bus_layout", {}))

    @mcp.tool(meta=MUTATING, tags=AUDIO)
    @enforce_preconditions
    async def add_audio_bus(
        name: str, volume_db: float = DEFAULT_AUDIO_BUS_VOLUME_DB, dry_run: bool = False
    ) -> AudioBusResult:
        """Add an audio bus named ``name`` (must be unique) at ``volume_db`` to the
        AudioServer layout. Returns its index. Route a player to it via the player's
        ``bus`` property, or attach effects with ``add_audio_bus_effect``.
        """
        if dry_run:
            return AudioBusResult(index=-1, name=name, dry_run=True)
        params = {"name": name, "volume_db": volume_db}
        return AudioBusResult(**await route(bridge, "cmd_add_audio_bus", params))

    @mcp.tool(meta=MUTATING, tags=AUDIO)
    @enforce_preconditions
    async def add_audio_bus_effect(
        bus: str,
        effect_type: str,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> AudioBusEffectResult:
        """Append an AudioEffect (``effect_type``, e.g. AudioEffectReverb /
        AudioEffectDelay / AudioEffectEQ) to the bus named ``bus``, configured with
        ``properties``. Returns the bus index and the new effect's stack index.
        """
        if dry_run:
            return AudioBusEffectResult(
                bus=bus, bus_index=-1, effect_type=effect_type, effect_index=-1, dry_run=True
            )
        params = {"bus": bus, "effect_type": effect_type, "properties": properties or {}}
        return AudioBusEffectResult(**await route(bridge, "cmd_add_audio_bus_effect", params))
