"""End-to-end scene session test: live Python bridge ↔ live Godot editor (issue #79).

Boots the headless editor and drives the full scene session roundtrip:
create a scene, open it, list open scenes, select nodes, save all,
and reload (confirm). This is the acceptance test that the scene session
tools work on a live Godot editor.
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
SCENE_A = "res://session_a.tscn"
SCENE_B = "res://session_b.tscn"
SCENE_A_FILE = GODOT_PROJECT / "session_a.tscn"
SCENE_B_FILE = GODOT_PROJECT / "session_b.tscn"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await bridge.send(command, params or {})
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_scene_open(bridge: Bridge, path: str = "") -> None:
    for _ in range(40):
        response = await bridge.send("cmd_get_active_scene")
        if response.ok and (response.result or {}).get("is_open"):
            if path == "" or (response.result or {}).get("path") == path:
                return
        await asyncio.sleep(0.25)
    raise AssertionError("the scene never became the active scene")


async def _cleanup() -> None:
    for f in [SCENE_A_FILE, SCENE_B_FILE]:
        uid = f.with_suffix(".tscn.uid")
        f.unlink(missing_ok=True)
        uid.unlink(missing_ok=True)


async def _run_roundtrip() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # Create two scene files to open/close/list.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCENE_A})
        await _wait_scene_open(bridge, SCENE_A)

        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCENE_B})
        await _wait_scene_open(bridge, SCENE_B)

        # list_open_scenes should report both A and B.
        listed = await _ok(bridge, "cmd_list_open_scenes")
        paths = [s["path"] for s in listed.get("scenes", [])]
        assert SCENE_A in paths and SCENE_B in paths

        # open_scene switches back to A.
        opened = await _ok(bridge, "cmd_open_scene", {"scene_path": SCENE_A})
        assert opened["opened"] is True
        active = await _ok(bridge, "cmd_get_active_scene")
        assert active["path"] == SCENE_A

        # already_open when re-opened.
        reopened = await _ok(bridge, "cmd_open_scene", {"scene_path": SCENE_A})
        assert reopened["already_open"] is True

        # select_nodes: create a child and select it.
        created = await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node2D", "name": "Box"}
        )
        assert created["created"] is True
        selected = await _ok(bridge, "cmd_select_nodes", {"node_paths": ["Box"]})
        assert selected["count"] == 1 and selected["selected"] == ["Box"]

        # save_all_scenes
        saved = await _ok(bridge, "cmd_save_all_scenes")
        assert saved["saved"] is True
        assert saved["count"] >= 2

        # reload_scene requires confirm
        blocked = await bridge.send("cmd_reload_scene", {"scene_path": SCENE_A, "confirm": False})
        assert blocked.ok is False and blocked.required == "confirm"

        # reload with confirm proceeds
        reloaded = await _ok(bridge, "cmd_reload_scene", {"scene_path": SCENE_A, "confirm": True})
        assert reloaded["reloaded"] is True

    finally:
        await bridge.close()
        await _cleanup()


def test_live_editor_scene_session_roundtrip() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_roundtrip())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        asyncio.run(_cleanup())
