"""Runtime session bridge tools (issue #66).

Control an editor *play session* and inspect the running game live. Play is launched
from the editor (so the game connects to the editor debugger, which the addon's
MCPDebugger captures); live inspection requires the godot-mcp runtime probe autoload in
the game. Foundation for input simulation (#36) and runtime inspection (#35). Gated in
the ``runtime`` toolset; play control is `runtime`, reads are `read_only`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import RUNTIME_TAG
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
