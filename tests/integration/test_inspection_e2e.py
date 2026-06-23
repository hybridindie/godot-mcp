"""End-to-end inspection test: live Python bridge ↔ live Godot editor (issue #5).

Boots the headless editor and exercises the cmd_* inspection handlers against the
real EditorInterface. The project has no scene open, so this also verifies the
graceful empty-state behaviour (acceptance: "works even when no scene is open").
Skipped when no Godot binary is present.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"


async def _run_checks() -> None:
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
        info = await bridge.send("cmd_get_project_info")
        assert info.ok and info.result is not None, info
        assert info.result["name"] == "godot-mcp"  # from godot/project.godot
        assert info.result["godot_version"].startswith("4.")
        assert info.result["project_path"]  # globalized res:// path to the project dir

        scene = await bridge.send("cmd_get_active_scene")
        assert scene.ok and scene.result is not None
        assert scene.result["is_open"] is False

        tree = await bridge.send("cmd_get_scene_tree")
        assert tree.ok and tree.result is not None
        assert tree.result["tree"] is None

        # No scene open ⇒ get_node_properties fails with a structured precondition.
        props = await bridge.send("cmd_get_node_properties", {"node_path": "Anything"})
        assert props.ok is False
        assert props.error == "PRECONDITION_FAILED"
        assert props.required == "active_scene"

        # The new single-property read handler is registered and routes the same way (#215).
        prop = await bridge.send(
            "cmd_get_node_property", {"node_path": "Anything", "property": "position"}
        )
        assert prop.ok is False
        assert prop.error == "PRECONDITION_FAILED"
        assert prop.required == "active_scene"
    finally:
        await bridge.close()


def test_live_editor_inspection() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        asyncio.run(_run_checks())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
