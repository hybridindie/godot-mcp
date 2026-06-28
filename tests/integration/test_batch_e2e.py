"""End-to-end batch / refactor test against a live editor (issue #48)."""

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
SCENE_A = "res://tmp_e2e_batch_a.tscn"
SCENE_B = "res://tmp_e2e_batch_b.tscn"
# .tscn files get a Godot 4.4+ .uid sidecar; clean both up.
ARTIFACTS = [
    GODOT_PROJECT / "tmp_e2e_batch_a.tscn",
    GODOT_PROJECT / "tmp_e2e_batch_a.tscn.uid",
    GODOT_PROJECT / "tmp_e2e_batch_b.tscn",
    GODOT_PROJECT / "tmp_e2e_batch_b.tscn.uid",
]


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
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # scene A: two Sprite2D + a plain Node, then save
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCENE_A})
        await _wait_scene_open(bridge)
        await _create(bridge, "S1", "Sprite2D")
        await _create(bridge, "S2", "Sprite2D")
        await _create(bridge, "Plain", "Node")

        # find_nodes_by_type finds both sprites
        found = await _ok(bridge, "cmd_find_nodes_by_type", {"type": "Sprite2D"})
        assert found["count"] == 2 and {n["name"] for n in found["nodes"]} == {"S1", "S2"}

        # batch_set by type: both sprites get visible=false
        batch = await _ok(
            bridge,
            "cmd_batch_set_property",
            {"type": "Sprite2D", "property": "visible", "value": False},
        )
        assert batch["count"] == 2 and batch["skipped"] == []

        # batch_set by explicit paths reports a node missing the property as skipped
        mixed = await _ok(
            bridge,
            "cmd_batch_set_property",
            {"node_paths": ["S1", "Plain"], "property": "centered", "value": False},
        )
        assert mixed["applied"] == ["S1"]
        assert mixed["skipped"] and mixed["skipped"][0]["path"] == "Plain"

        await _ok(bridge, "cmd_save_scene", {})

        # open scene B so A is no longer the currently-edited scene
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCENE_B})
        await _wait_scene_open(bridge)

        # cross-scene edit of A (a file not currently edited) succeeds on disk
        cross = await _ok(
            bridge,
            "cmd_cross_scene_set_property",
            {"scenes": [SCENE_A], "type": "Sprite2D", "property": "visible", "value": True},
        )
        a_result = cross["results"][0]
        assert a_result["modified"] == 2 and a_result["error"] == ""
        assert cross["total_modified"] == 2

        # the currently-edited scene (B) is skipped with an explicit error
        guarded = await _ok(
            bridge,
            "cmd_cross_scene_set_property",
            {"scenes": [SCENE_B], "type": "Node2D", "property": "visible", "value": False},
        )
        assert guarded["results"][0]["modified"] == 0
        assert "edited" in guarded["results"][0]["error"]

        # dry_run reports the plan without an error, still counting matches
        dry = await _ok(
            bridge,
            "cmd_cross_scene_set_property",
            {
                "scenes": [SCENE_A],
                "type": "Sprite2D",
                "property": "visible",
                "value": False,
                "dry_run": True,
            },
        )
        assert dry["dry_run"] is True and dry["results"][0]["modified"] == 2

        # dependency analysis runs and returns a (possibly empty) list
        deps = await _ok(bridge, "cmd_get_dependencies", {"path": SCENE_A})
        assert isinstance(deps["dependencies"], list)

        # validation: unknown scene path and missing target selector
        missing = await bridge.send("cmd_get_dependencies", {"path": "res://nope.tscn"})
        assert missing.ok is False and missing.error == "RESOURCE_NOT_FOUND"
        no_target = await bridge.send(
            "cmd_batch_set_property", {"property": "visible", "value": True}
        )
        assert no_target.ok is False and no_target.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_batch() -> None:
    assert GODOT_BIN is not None
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
        for artifact in ARTIFACTS:
            artifact.unlink(missing_ok=True)
