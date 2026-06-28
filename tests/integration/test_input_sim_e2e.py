"""End-to-end input simulation test against a live editor (issue #36).

Rides on the #66 runtime-session bridge: register the probe autoload, play a scene, then
synthesize input and confirm the running game acknowledges each injected event.
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
SCRATCH = "res://tmp_e2e_input_sim.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_input_sim.tscn"
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


async def _wait_connected(bridge: Bridge) -> None:
    for _ in range(30):
        state = await _ok(bridge, "cmd_get_game_scene_tree", {})
        if state.get("connected"):
            return
        await asyncio.sleep(0.5)
    raise AssertionError("probe never connected")


async def _wait_injected(bridge: Bridge, at_least: int) -> int:
    for _ in range(20):
        stats = await _ok(bridge, "cmd_get_input_stats", {})
        if stats["injected"] >= at_least:
            return int(stats["injected"])
        await asyncio.sleep(0.25)
    raise AssertionError(f"injected count never reached {at_least}")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # precondition: input with no play session is a structured error
        no_session = await bridge.send("cmd_simulate_key", {"key": "Space"})
        assert no_session.ok is False and no_session.error == "PRECONDITION_FAILED"
        assert no_session.required == "play_session"

        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await _wait_connected(bridge)

        # synthesize three single events; the game acknowledges each
        await _ok(bridge, "cmd_simulate_key", {"key": "Space", "pressed": True})
        await _ok(bridge, "cmd_simulate_mouse", {"x": 32, "y": 48, "button": "left"})
        await _ok(bridge, "cmd_simulate_action", {"action": "ui_accept"})
        await _wait_injected(bridge, 3)

        # a sequence injects each of its events too
        seq = await _ok(
            bridge,
            "cmd_play_input_sequence",
            {
                "events": [
                    {"type": "key", "key": "A"},
                    {"type": "mouse", "x": 1, "y": 1},
                ],
                "delay_ms": 20,
            },
        )
        assert seq["count"] == 2
        await _wait_injected(bridge, 5)

        # validation: empty key, unknown mouse button, and a malformed sequence event
        bad_key = await bridge.send("cmd_simulate_key", {"key": ""})
        assert bad_key.ok is False and bad_key.error == "VALIDATION_ERROR"
        bad_button = await bridge.send("cmd_simulate_mouse", {"x": 0, "y": 0, "button": "nope"})
        assert bad_button.ok is False and bad_button.error == "VALIDATION_ERROR"
        bad_seq = await bridge.send("cmd_play_input_sequence", {"events": [{"type": "bogus"}]})
        assert bad_seq.ok is False and bad_seq.error == "VALIDATION_ERROR"

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_input_sim() -> None:
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
        PROJECT_GODOT.write_bytes(snapshot)
