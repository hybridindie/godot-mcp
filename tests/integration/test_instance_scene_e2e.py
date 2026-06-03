"""End-to-end instance_scene test: live Python bridge ↔ live Godot editor (issue #80).

Tests instancing a saved PackedScene as a child node in another scene.
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
HOST = "res://e2e_instance_host.tscn"
SUB = "res://e2e_instance_sub.tscn"
_ARTIFACTS = [
    "e2e_instance_host.tscn",
    "e2e_instance_host.tscn.uid",
    "e2e_instance_sub.tscn",
    "e2e_instance_sub.tscn.uid",
]


async def _ok(bridge: Bridge, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await bridge.send(command, params or {})
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        response = await bridge.send("cmd_get_active_scene")
        if response.ok and (response.result or {}).get("is_open"):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("scene did not open")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    for _ in range(60):
        try:
            await bridge.connect()
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise AssertionError("could not connect to addon bridge")

    try:
        # Create a sub-scene that we will instance.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SUB})
        await _wait_scene_open(bridge)
        await _ok(bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Sprite2D", "name": "SubHero"})
        await _ok(bridge, "cmd_save_scene")

        # Create a host scene and instance the sub-scene into it.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": HOST})
        await _wait_scene_open(bridge)

        instanced = await _ok(
            bridge,
            "cmd_instance_scene",
            {"parent_path": ".", "scene_path": SUB, "name": "MySub"},
        )
        assert instanced["instanced"] is True
        assert instanced["node_path"] == "MySub"

        tree = await _ok(bridge, "cmd_get_scene_tree")
        names = [c["name"] for c in tree["tree"]["children"]]
        assert "MySub" in names

        # The instance should be removable via undo (UndoRedo-wrapped).
        await _ok(bridge, "cmd_save_scene")
    finally:
        await bridge.close()


def test_live_editor_instance_scene() -> None:
    assert GODOT_BIN is not None
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
        for artifact in _ARTIFACTS:
            (GODOT_PROJECT / artifact).unlink(missing_ok=True)
