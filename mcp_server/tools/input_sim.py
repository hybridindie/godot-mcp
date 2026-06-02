"""Input simulation tools (issue #36).

Drive a *running* game over the bridge: synthesize key/mouse/action input, play input
sequences, and record the input the game receives for replay (#68). Built on the #66
runtime-session rails — the game must be running from the editor with the godot-mcp
runtime probe autoload, which receives ``godot_mcp:`` input messages and calls
``Input.parse_input_event`` / ``Input.action_press`` on itself (and buffers events via
its ``_input`` hook while recording). Gated `input` toolset; injection/recording-control
is `runtime`, reads are `read_only`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import INPUT_TAG
from mcp_server.models.input_sim import (
    InputStatsResult,
    RecordingResult,
    RecordResult,
    SimInputResult,
)
from mcp_server.safety import READ_ONLY, RUNTIME
from mcp_server.tools._route import route

INPUT = {INPUT_TAG}


def register_input_sim(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the input simulation tools."""

    @mcp.tool(meta=RUNTIME, tags=INPUT)
    async def simulate_key(
        key: str,
        pressed: bool = True,
        shift: bool = False,
        ctrl: bool = False,
        alt: bool = False,
        meta: bool = False,
    ) -> SimInputResult:
        """Send a key event to the running game. ``key`` is a Godot key name
        ("A", "Space", "Enter", "Escape", …); ``pressed`` false sends a release. Optional
        modifier flags (shift/ctrl/alt/meta). Requires a play session + runtime probe.
        """
        params = {
            "key": key,
            "pressed": pressed,
            "shift": shift,
            "ctrl": ctrl,
            "alt": alt,
            "meta": meta,
        }
        return SimInputResult(**await route(bridge, "cmd_simulate_key", params))

    @mcp.tool(meta=RUNTIME, tags=INPUT)
    async def simulate_mouse(
        x: float,
        y: float,
        button: str = "",
        pressed: bool = True,
        relative_x: float = 0.0,
        relative_y: float = 0.0,
    ) -> SimInputResult:
        """Send a mouse event at viewport position (``x``, ``y``). With ``button`` empty,
        sends motion (with optional ``relative_x``/``relative_y``); with ``button`` =
        left/right/middle/wheel_up/wheel_down, sends a button press/release (``pressed``).
        """
        params = {
            "x": x,
            "y": y,
            "button": button,
            "pressed": pressed,
            "relative_x": relative_x,
            "relative_y": relative_y,
        }
        return SimInputResult(**await route(bridge, "cmd_simulate_mouse", params))

    @mcp.tool(meta=RUNTIME, tags=INPUT)
    async def simulate_action(
        action: str, pressed: bool = True, strength: float = 1.0
    ) -> SimInputResult:
        """Press or release an input-map action (e.g. "ui_accept", "jump") on the running
        game. ``strength`` (0..1) applies to a press. The action must exist in the
        project's Input Map.
        """
        params = {"action": action, "pressed": pressed, "strength": strength}
        return SimInputResult(**await route(bridge, "cmd_simulate_action", params))

    @mcp.tool(meta=RUNTIME, tags=INPUT)
    async def play_input_sequence(
        events: list[dict[str, Any]], delay_ms: int = 0
    ) -> SimInputResult:
        """Play a sequence of input events in order, ``delay_ms`` apart. Each event is a
        dict with ``type`` = "key" | "mouse" | "action" and that type's fields (as for
        the simulate_* tools, e.g. ``{"type":"key","key":"Space","pressed":true}``).
        """
        params = {"events": events, "delay_ms": delay_ms}
        return SimInputResult(**await route(bridge, "cmd_play_input_sequence", params))

    @mcp.tool(meta=READ_ONLY, tags=INPUT)
    async def get_input_stats() -> InputStatsResult:
        """Report how many synthesized input events the running game has acknowledged —
        use it to confirm injected input is reaching the game.
        """
        return InputStatsResult(**await route(bridge, "cmd_get_input_stats", {}))

    @mcp.tool(meta=RUNTIME, tags=INPUT)
    async def record_input(include_motion: bool = False) -> RecordResult:
        """Start recording the input the running game receives (key + mouse button;
        mouse motion only when ``include_motion``). Stop and collect it with
        ``stop_recording``; the result feeds straight back into ``play_input_sequence``.
        """
        params = {"include_motion": include_motion}
        return RecordResult(**await route(bridge, "cmd_record_input", params))

    @mcp.tool(meta=READ_ONLY, tags=INPUT)
    async def stop_recording(timeout_ms: int = 2000) -> RecordingResult:
        """Stop recording and return the captured ``events`` (in the
        ``play_input_sequence`` format). Polls the addon up to ``timeout_ms`` for the
        buffered sequence.
        """
        await route(bridge, "cmd_stop_recording", {})
        attempts = max(1, timeout_ms // 100)
        result: dict[str, Any] = {"ready": False, "connected": False, "events": []}
        for _ in range(attempts):
            result = await route(bridge, "cmd_get_recording", {})
            if result.get("ready"):
                break
            await asyncio.sleep(0.1)
        return RecordingResult(**result)
