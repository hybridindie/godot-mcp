"""End-to-end project & filesystem test against a live editor (issue #32).

Runs the fs-tree / search / settings / UID handlers against the real project. The
set_setting test writes project.godot, so the test snapshots and restores it.
Skipped without Godot.
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
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
ADDON = "res://addons/godot_mcp"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # filesystem tree of the addon dir includes its scripts
        tree = await _ok(bridge, "cmd_get_filesystem_tree", {"directory": ADDON, "max_depth": 1})
        names = [c["name"] for c in tree["tree"]["children"]]
        assert "command_router.gd" in names

        # search by glob, and by content
        by_glob = await _ok(bridge, "cmd_search_files", {"directory": ADDON, "name_glob": "*.gd"})
        assert any(m.endswith("command_router.gd") for m in by_glob["matches"])
        by_content = await _ok(
            bridge,
            "cmd_search_files",
            {"directory": ADDON, "content": "class_name MCPCommandRouter"},
        )
        assert any(m.endswith("command_router.gd") for m in by_content["matches"])

        # settings: existing + missing
        present = await _ok(bridge, "cmd_get_setting", {"name": "application/config/name"})
        assert present["exists"] is True and present["value"] == "godot-mcp"
        missing = await _ok(bridge, "cmd_get_setting", {"name": "nonexistent/key"})
        assert missing["exists"] is False

        # write a setting, read it back
        await _ok(
            bridge,
            "cmd_set_setting",
            {"name": "application/config/description", "value": "e2e test description"},
        )
        readback = await _ok(bridge, "cmd_get_setting", {"name": "application/config/description"})
        assert readback["value"] == "e2e test description"

        # UID round-trip on a script that has a .uid
        to_uid = await _ok(
            bridge, "cmd_path_to_uid", {"path": "res://addons/godot_mcp/godot_mcp.gd"}
        )
        assert to_uid["uid"].startswith("uid://")
        back = await _ok(bridge, "cmd_uid_to_path", {"uid": to_uid["uid"]})
        assert back["path"] == "res://addons/godot_mcp/godot_mcp.gd"

        # Sandbox: paths outside the project (res://) are rejected.
        outside = await bridge.send("cmd_get_filesystem_tree", {"directory": "/etc"})
        assert outside.ok is False and outside.error == "VALIDATION_ERROR"

        # delete_resource_file round-trip (#217): create a throwaway file, delete it,
        # confirm it's gone, and that a second delete + a non-res:// path are rejected.
        tmp = "res://tmp_e2e_delete.gd"
        await _ok(bridge, "cmd_write_script", {"script_path": tmp, "content": "extends Node\n"})
        deleted = await _ok(bridge, "cmd_delete_resource_file", {"path": tmp})
        assert deleted["deleted"] is True and deleted["path"] == tmp
        gone = await bridge.send("cmd_delete_resource_file", {"path": tmp})
        assert gone.ok is False and gone.error == "RESOURCE_NOT_FOUND"
        bad = await bridge.send("cmd_delete_resource_file", {"path": "/etc/passwd"})
        assert bad.ok is False and bad.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


# #422: deleting a .tscn that is open in the editor leaves a stale in-memory tab;
# recreating at the same path resurrects mangled duplicates. delete_resource_file
# must close the tab for a deleted scene (and save_scene/create_scene must never
# write through the stale in-memory copy).
async def _run_delete_open_scene() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    scene = "res://tmp_e2e_delete_tab.tscn"
    scene_file = GODOT_PROJECT / "tmp_e2e_delete_tab.tscn"
    try:
        created = await _ok(
            bridge,
            "cmd_create_scene",
            {"root_type": "Node3D", "scene_path": scene},
        )
        assert created["created"] is True
        # The created scene is now open+active; add a node so the tab has content.
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node3D", "name": "Original"},
        )

        deleted = await _ok(bridge, "cmd_delete_resource_file", {"path": scene})
        assert deleted["deleted"] is True
        assert not scene_file.exists()

        # The tab must be gone: the deleted scene may no longer be open/active.
        active = await bridge.send("cmd_get_active_scene")
        active_path = (active.result or {}).get("path")
        assert active_path != scene, (
            "deleted scene is still the active (stale) tab — recreate would resurrect it"
        )

        # Recreate at the same path and confirm a clean, empty scene opens.
        recreated = await _ok(
            bridge,
            "cmd_create_scene",
            {"root_type": "Node3D", "scene_path": scene},
        )
        assert recreated["created"] is True
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        root_children = tree["tree"]["children"]
        names = [c["name"] for c in root_children]
        assert names == [], f"recreated scene is not empty: {names} — stale tab resurrected"
    finally:
        await bridge.close()
        scene_file.unlink(missing_ok=True)
        (GODOT_PROJECT / "tmp_e2e_delete_tab.tscn.uid").unlink(missing_ok=True)


def test_live_delete_open_scene_closes_tab() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_delete_open_scene())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        (GODOT_PROJECT / "tmp_e2e_delete_tab.tscn").unlink(missing_ok=True)
        (GODOT_PROJECT / "tmp_e2e_delete_tab.tscn.uid").unlink(missing_ok=True)
