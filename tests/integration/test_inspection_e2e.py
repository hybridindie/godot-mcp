"""End-to-end inspection test: live Python bridge ↔ live Godot editor (issue #5).

Boots the headless editor and exercises the cmd_* inspection handlers against the
real EditorInterface. The project has no scene open, so this also verifies the
graceful empty-state behaviour (acceptance: "works even when no scene is open").
Skipped when no Godot binary is present.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    serve_and_await_editor,
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# Ephemeral per-run port (issue #444): no fixed port, so a concurrent
# job's (or an orphaned) editor can never connect to this test's listener.
BRIDGE_URL = e2e_bridge_url()


async def _run_checks() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

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

        # The new group-read handler is registered and routes the same way (#216).
        groups = await bridge.send("cmd_get_node_groups", {"node_path": "Anything"})
        assert groups.ok is False
        assert groups.error == "PRECONDITION_FAILED"
        assert groups.required == "active_scene"

        # #797: the four node handlers share one resolver and echo the NORMALIZED
        # path ("root/" and a leading "/" are stripped), so a caller can compare
        # the response to the path it passed without re-normalizing it.
        scene_path = f"res://tmp_inspection_norm_{uuid.uuid4().hex[:8]}.tscn"
        try:
            created = await bridge.send(
                "cmd_create_scene", {"root_type": "Node2D", "scene_path": scene_path}
            )
            assert created.ok, created
            for _ in range(40):
                active = await bridge.send("cmd_get_active_scene")
                if active.ok and (active.result or {}).get("path") == scene_path:
                    break
                await asyncio.sleep(0.25)
            made = await bridge.send(
                "cmd_create_node",
                {"parent_path": ".", "node_type": "Node2D", "name": "Holder"},
            )
            assert made.ok, made
            for command in ("cmd_get_node_groups", "cmd_get_node_property_list"):
                response = await bridge.send(command, {"node_path": "root/Holder"})
                assert response.ok, response
                assert response.result["node_path"] == "Holder", response.result
            exists = await bridge.send("cmd_node_exists", {"node_path": "/root/Holder"})
            assert exists.ok and exists.result["exists"] is True, exists
            props = await bridge.send("cmd_get_node_properties", {"node_path": "root/Holder"})
            assert props.ok and props.result["node_path"] == "Holder", props
        finally:
            await bridge.send(
                "cmd_delete_resource_file", {"path": scene_path, "confirm": True}
            )
    finally:
        await bridge.close()


def test_live_editor_inspection() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_checks())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
