"""Runtime session bridge tools (issue #66).

Control an editor *play session* and inspect the running game live. Play is launched
from the editor (so the game connects to the editor debugger, which the addon's
MCPDebugger captures); live inspection requires the godot-mcp runtime probe autoload in
the game. Foundation for input simulation (#36) and runtime inspection (#35). Gated in
the ``runtime`` toolset; play control is `runtime`, reads are `read_only`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import uuid
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from mcp_server.bridge import Bridge
from mcp_server.categories import RUNTIME_TAG
from mcp_server.constraints import TimeoutMs
from mcp_server.defaults import DEFAULT_CAPTURE_TIMEOUT_MS, DEFAULT_POLL_INTERVAL_SECONDS
from mcp_server.models.runtime_session import GameSceneTreeResult, PlayResult
from mcp_server.safety import READ_ONLY, RUNTIME
from mcp_server.tools._route import route

RUNTIME_SET = {RUNTIME_TAG}


def register_runtime_session(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the play-control + live-inspection tools."""

    @mcp.tool(meta=RUNTIME, tags=RUNTIME_SET)
    async def play_scene(scene_path: str = "") -> PlayResult:
        """Run the game from the editor: play ``scene_path`` (a ``res://*.tscn``) or the
        project's main scene when omitted. The game connects to the editor debugger, so
        runtime inspection/input tools can reach it.

        WHEN TO USE: You need to interact with the running game (simulate input,
        inspect live nodes, debug, test assertions).
        WHEN NOT TO USE: Headless CI/automation without an editor — use
        run_and_capture() instead. That runs Godot in a subprocess and returns
        logs without an editor session.

        IF THIS FAILS with "scene not found":
          -> The scene_path is wrong. Use get_project_info() to find the main scene,
             or get_scene_tree() to see available scenes.
        IF THIS FAILS with "editor not connected":
          -> The Godot editor is not running or the addon is disabled. Check
             get_server_info() for bridge state and follow the troubleshoot prompt.
        """
        params = {"scene_path": scene_path}
        return PlayResult(**await route(bridge, "cmd_play_scene", params))

    @mcp.tool(meta=RUNTIME, tags=RUNTIME_SET)
    async def stop_scene() -> PlayResult:
        """Stop the current editor play session."""
        return PlayResult(**await route(bridge, "cmd_stop_scene", {}))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def is_playing() -> PlayResult:
        """Report whether a play session is running and which scene."""
        return PlayResult(**await route(bridge, "cmd_is_playing", {}))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def get_game_scene_tree() -> GameSceneTreeResult:
        """Get the *running* game's live scene tree ({name, type, path, children}).
        Requires an active play session with the godot-mcp runtime probe autoload; if the
        probe isn't connected, returns ``connected=false`` with a ``hint`` to add it.

        WHEN TO USE: You need to inspect node hierarchy, positions, or state while
        the game is actively running (e.g., after simulating input to verify movement).
        WHEN NOT TO USE: The editor is idle with no play session — use
        get_scene_tree() to read the static scene structure instead.
        """
        return GameSceneTreeResult(**await route(bridge, "cmd_get_game_scene_tree", {}))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def capture_game_screenshot(
        timeout_ms: TimeoutMs = DEFAULT_CAPTURE_TIMEOUT_MS,
    ) -> Image:
        """Capture the *running game's* rendered viewport as a PNG image, so you can
        visually verify what the player sees — including shader, lighting, and camera
        output the editor viewport cannot show (the game is a separate process; the
        probe grabs the frame in-process). Read-only. Requires an active play session
        with the runtime probe autoload.

        IF THIS FAILS with "No play session":
          -> Call play_scene(scene_path) first.
        IF THIS FAILS with "probe is not connected":
          -> Register MCPRuntimeProbe as an autoload in the game (get_project_info()
             to check), then play_scene again.
        """
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
        # Stable per-invocation id (constant across the poll loop): the addon dispatches
        # one probe grab per request_id and matches the cached frame by it (mirrors
        # find_ui_elements) — polls without it would never trigger the dispatch.
        params = {"request_id": uuid.uuid4().hex}
        result: dict[str, Any] = {}
        while True:
            result = await route(bridge, "cmd_capture_game_screenshot", params)
            # Done when the probe's frame arrived; ``{"ready": false}`` means the
            # grab is still pending (the addon dispatches one request per poll).
            if result.get("base64") or (result.get("ready") and result.get("error")):
                break
            if asyncio.get_event_loop().time() >= deadline:
                raise ToolError(
                    f"Game frame capture did not complete within {timeout_ms}ms — "
                    "is the game window rendering (not fully hidden/minimized)?"
                )
            await asyncio.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
        if not result.get("base64"):
            reason = str(result.get("error", "")).strip()
            detail = f" ({reason})" if reason else ""
            raise ToolError(f"Game frame capture returned no image data.{detail}")
        try:
            data = base64.b64decode(result["base64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"Game frame data was not valid base64: {exc}") from exc
        # Normalize e.g. "image/png" → "png".
        fmt = str(result.get("format", "png")).removeprefix("image/")
        return Image(data=data, format=fmt)
