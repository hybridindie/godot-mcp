"""End-to-end animation test against a live editor (issue #39)."""

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
SCRATCH = "res://tmp_e2e_animation.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_animation.tscn"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _create(bridge: Bridge, name: str, node_type: str, parent: str = ".") -> None:
    await _ok(
        bridge, "cmd_create_node", {"parent_path": parent, "node_type": node_type, "name": name}
    )


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("is_open"):
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
        raise AssertionError("could not connect to the addon bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _create(bridge, "Sprite2D", "Sprite2D")
        await _create(bridge, "AnimationPlayer", "AnimationPlayer")

        # create an animation, add a track, insert a keyframe
        anim = await _ok(
            bridge,
            "cmd_create_animation",
            {"node_path": "AnimationPlayer", "name": "walk", "length": 2.0},
        )
        assert anim["animation"] == "walk" and anim["length"] == 2.0
        track = await _ok(
            bridge,
            "cmd_add_animation_track",
            {
                "node_path": "AnimationPlayer",
                "animation": "walk",
                "track_path": "Sprite2D:position",
            },
        )
        assert track["track"] == 0
        key = await _ok(
            bridge,
            "cmd_insert_keyframe",
            {
                "node_path": "AnimationPlayer",
                "animation": "walk",
                "track": 0,
                "time": 0.5,
                "value": "Vector2(10, 20)",
            },
        )
        assert key["time"] == 0.5

        # AnimationTree with a state-machine root + a state
        tree = await _ok(
            bridge,
            "cmd_create_animation_tree",
            {"parent_path": ".", "name": "SM", "anim_player": "AnimationPlayer"},
        )
        assert tree["node_path"] == "SM"
        state = await _ok(
            bridge,
            "cmd_add_state_machine_state",
            {"tree_path": "SM", "state_name": "idle", "animation": "walk"},
        )
        assert state["state"] == "idle"

        # a separate blend-tree AnimationTree
        await _ok(
            bridge,
            "cmd_create_animation_tree",
            {"parent_path": ".", "name": "BT", "root_type": "AnimationNodeBlendTree"},
        )
        blend = await _ok(
            bridge,
            "cmd_set_blend_tree_node",
            {"tree_path": "BT", "node_name": "anim", "node_type": "AnimationNodeAnimation"},
        )
        assert blend["node_type"] == "AnimationNodeAnimation"

        # validation: non-player target, duplicate name, wrong tree root, bad node type
        bad_player = await bridge.send(
            "cmd_create_animation", {"node_path": "Sprite2D", "name": "x"}
        )
        assert bad_player.ok is False and bad_player.error == "VALIDATION_ERROR"
        dup = await bridge.send(
            "cmd_create_animation", {"node_path": "AnimationPlayer", "name": "walk"}
        )
        assert dup.ok is False and dup.error == "VALIDATION_ERROR"
        wrong_root = await bridge.send(
            "cmd_set_blend_tree_node",
            {"tree_path": "SM", "node_name": "n", "node_type": "AnimationNodeAnimation"},
        )
        assert wrong_root.ok is False and wrong_root.error == "VALIDATION_ERROR"
        bad_type = await bridge.send(
            "cmd_set_blend_tree_node", {"tree_path": "BT", "node_name": "n", "node_type": "Node2D"}
        )
        assert bad_type.ok is False and bad_type.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_animation() -> None:
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
        SCRATCH_FILE.unlink(missing_ok=True)
