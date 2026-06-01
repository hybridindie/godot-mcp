"""End-to-end mutation test: live Python bridge ↔ live Godot editor (issue #6).

Boots the headless editor and drives a full mutation roundtrip — create a scene,
add a node, set a property, rename, save, and delete (with/without confirm) —
against the real EditorInterface + EditorUndoRedoManager. This is the acceptance
test "all mutation tools work on a live Godot scene". Skipped without Godot.
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
SCRATCH = "res://e2e_scratch.tscn"
SCRATCH_FILE = GODOT_PROJECT / "e2e_scratch.tscn"


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
    raise AssertionError("the created scene never became the active scene")


async def _run_roundtrip() -> None:
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

        created = await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Sprite2D", "name": "Hero"}
        )
        assert created["created"] is True and created["node_path"] == "Hero"

        was_set = await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Hero", "property": "position", "value": {"x": 10, "y": 20}},
        )
        assert was_set["value"] == {"x": 10.0, "y": 20.0}  # coerced JSON → Vector2 → JSON

        renamed = await _ok(bridge, "cmd_rename_node", {"node_path": "Hero", "new_name": "Player"})
        assert renamed["new_name"] == "Player"

        tree = await _ok(bridge, "cmd_get_scene_tree")
        names = [c["name"] for c in tree["tree"]["children"]]
        assert "Player" in names and "Hero" not in names

        saved = await _ok(bridge, "cmd_save_scene")
        assert saved["saved"] is True and saved["path"] == SCRATCH

        # Destructive guard is honored addon-side too.
        blocked = await bridge.send("cmd_delete_node", {"node_path": "Player", "confirm": False})
        assert blocked.ok is False and blocked.required == "confirm"

        deleted = await _ok(bridge, "cmd_delete_node", {"node_path": "Player", "confirm": True})
        assert deleted["deleted"] is True

        after = await _ok(bridge, "cmd_get_scene_tree")
        assert "Player" not in [c["name"] for c in after["tree"]["children"]]
    finally:
        await bridge.close()


def test_live_editor_mutation_roundtrip() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        asyncio.run(_run_roundtrip())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        SCRATCH_FILE.unlink(missing_ok=True)
