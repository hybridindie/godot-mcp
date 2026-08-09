"""End-to-end input recording test against a live editor (issue #68).

On the #66 rails: synthesized input (Input.parse_input_event) also generates _input
calls, so the probe's recording hook captures it — record, inject, stop, and the
captured events come back in the play_input_sequence format (then replay them).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, needs_display, serve_and_await_editor

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    needs_display,
]

BRIDGE_URL = "ws://127.0.0.1:9097"
SCRATCH = "res://tmp_e2e_input_rec.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_input_rec.tscn"
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


async def _wait_injected(bridge: Bridge, at_least: int) -> None:
    for _ in range(20):
        if (await _ok(bridge, "cmd_get_input_stats", {}))["injected"] >= at_least:
            return
        await asyncio.sleep(0.25)
    raise AssertionError("injected count not reached")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # precondition: recording with no play session is a structured error
        no_session = await bridge.send("cmd_record_input", {})
        assert no_session.ok is False and no_session.error == "PRECONDITION_FAILED"

        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await _wait_connected(bridge)

        # record, then synthesize input (parse_input_event also fires _input -> captured)
        await _ok(bridge, "cmd_record_input", {})
        await _ok(bridge, "cmd_simulate_key", {"key": "Space", "pressed": True})
        await _ok(bridge, "cmd_simulate_mouse", {"x": 7, "y": 9, "button": "left"})
        await _wait_injected(bridge, 2)
        await asyncio.sleep(0.3)  # let the _input callbacks land in the buffer
        await _ok(bridge, "cmd_stop_recording", {})

        events: list[dict[str, Any]] = []
        for _ in range(30):
            rec = await _ok(bridge, "cmd_get_recording", {})
            if rec.get("ready"):
                events = rec["events"]
                break
            await asyncio.sleep(0.2)
        kinds = {e["type"] for e in events}
        assert "key" in kinds, f"no key event captured: {events}"
        assert any(e["type"] == "key" and e.get("key") == "Space" for e in events)
        assert any(e["type"] == "mouse" and e.get("button") == "left" for e in events)

        # the captured sequence replays straight back through play_input_sequence
        replayed = await _ok(bridge, "cmd_play_input_sequence", {"events": events})
        assert replayed["sent"] is True

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_input_recording() -> None:
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
