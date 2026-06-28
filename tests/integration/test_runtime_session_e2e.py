"""End-to-end runtime session bridge test against a live editor (issue #66).

Validated headless: play control, the not-connected path (no probe autoload), and the
full debugger round-trip (register probe -> play -> live scene tree via MCPDebugger).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, serve_and_await_editor

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://127.0.0.1:9097"
SCRATCH = "res://tmp_e2e_runtime_session.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_runtime_session.tscn"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
PROBE = "res://addons/godot_mcp/mcp_runtime_probe.gd"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("is_open"):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("scene did not open")


async def _wait_playing(bridge: Bridge, want: bool) -> None:
    for _ in range(20):
        state = await _ok(bridge, "cmd_is_playing", {})
        if state["playing"] is want:
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"is_playing never became {want}")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # precondition: querying the live tree with nothing playing is a structured error
        not_playing = await bridge.send("cmd_get_game_scene_tree", {})
        assert not_playing.ok is False and not_playing.error == "PRECONDITION_FAILED"
        assert not_playing.required == "play_session"

        # play WITHOUT the probe autoload -> playing, but not connected to a probe
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await _wait_playing(bridge, True)
        no_probe = await _ok(bridge, "cmd_get_game_scene_tree", {})
        assert no_probe["playing"] is True and no_probe["connected"] is False
        assert no_probe["tree"] is None and "probe" in no_probe["hint"]
        await _ok(bridge, "cmd_stop_scene", {})
        await _wait_playing(bridge, False)

        # register the probe autoload, then play -> the live tree comes back
        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        tree: dict[str, Any] | None = None
        for _ in range(30):
            state = await _ok(bridge, "cmd_get_game_scene_tree", {})
            if state["connected"] and state["tree"]:
                tree = state["tree"]
                break
            await asyncio.sleep(0.5)
        assert tree is not None, "probe never delivered the live scene tree"
        assert tree["type"] == "Window"  # the game's root viewport
        child_types = [c["type"] for c in tree["children"]]
        assert "Node2D" in child_types  # our played scene root
        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_runtime_session() -> None:
    assert GODOT_BIN is not None
    snapshot = PROJECT_GODOT.read_bytes()
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        SCRATCH_FILE.unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)  # restore (drop the probe autoload)
