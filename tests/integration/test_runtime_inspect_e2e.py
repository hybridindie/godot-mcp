"""End-to-end runtime inspection test against a live editor (issue #35).

On the #66 rails: build a scene with a Button, play it, then locate the live UI element
and monitor a property over time via the runtime probe.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"
SCRATCH = "res://tmp_e2e_runtime_inspect.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_runtime_inspect.tscn"
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


async def _poll(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    for _ in range(30):
        r = await _ok(bridge, command, params)
        if r.get("ready"):
            return r
        await asyncio.sleep(0.2)
    raise AssertionError(f"{command} never became ready")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    for _ in range(60):
        try:
            await bridge.connect()
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise AssertionError("could not connect to the addon bridge")

    try:
        # build a scene with a Button, then save it so the played process loads it
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Button", "name": "Start"}
        )
        await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Start", "property": "text", "value": "Play"},
        )
        await _ok(bridge, "cmd_save_scene", {})

        # precondition: inspection with no play session is a structured error
        no_session = await bridge.send(
            "cmd_monitor_property", {"node_path": "/root/x", "property": "position"}
        )
        assert no_session.ok is False and no_session.error == "PRECONDITION_FAILED"

        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await _wait_connected(bridge)

        # find the live Button (with text + rect)
        found = await _poll(bridge, "cmd_find_ui_elements", {"class_filter": "Button"})
        buttons = [e for e in found["elements"] if e["name"] == "Start"]
        assert buttons, f"Start button not found in {found['elements']}"
        button = buttons[0]
        assert button["node_class"] == "Button"
        assert button["text"] == "Play"
        assert "rect" in button and button["visible"] is True

        # monitor a property over time on that live node
        await _ok(
            bridge,
            "cmd_monitor_property",
            {"node_path": button["path"], "property": "position", "samples": 5},
        )
        samples = await _poll(bridge, "cmd_get_property_samples", {})
        assert samples["error"] == ""
        assert len(samples["samples"]) == 5
        assert "value" in samples["samples"][0]

        # monitoring an invalid property reports an error (not a crash)
        await _ok(
            bridge,
            "cmd_monitor_property",
            {"node_path": button["path"], "property": "no_such_property_xyz", "samples": 3},
        )
        bad = await _poll(bridge, "cmd_get_property_samples", {})
        assert bad["error"] != ""

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_runtime_inspect() -> None:
    assert GODOT_BIN is not None
    snapshot = PROJECT_GODOT.read_bytes()
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
