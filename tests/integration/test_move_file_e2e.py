"""End-to-end move-file test against a live editor (issue #532).

Creates a script + a scene referencing it, moves the script with the mover,
and verifies the referencing scene was rewritten — plus the unsaved-scene
refusal (#532 precondition case).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    needs_display,
    serve_and_await_editor,
)

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    needs_display,
]

BRIDGE_URL = e2e_bridge_url()
OLD_SCRIPT = "res://tmp_e2e_moved.gd"
NEW_SCRIPT = "res://tmp_e2e_moved_renamed.gd"
REF_SCENE = "res://tmp_e2e_moved_ref.tscn"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
FILES = [
    GODOT_PROJECT / "tmp_e2e_moved.gd",
    GODOT_PROJECT / "tmp_e2e_moved.gd.uid",
    GODOT_PROJECT / "tmp_e2e_moved_renamed.gd",
    GODOT_PROJECT / "tmp_e2e_moved_renamed.gd.uid",
    GODOT_PROJECT / "tmp_e2e_moved_ref.tscn",
    GODOT_PROJECT / "tmp_e2e_moved_ref.tscn.uid",
]


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


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # A script referenced by a scene that is open in the editor.
        await _ok(
            bridge,
            "cmd_write_script",
            {"script_path": OLD_SCRIPT, "content": "@tool\nextends Node\nvar x := 1\n"},
        )
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node", "scene_path": REF_SCENE})
        await _wait_scene_open(bridge)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node", "name": "User"}
        )
        await _ok(
            bridge, "cmd_attach_script", {"node_path": "User", "script_path": OLD_SCRIPT}
        )
        await _ok(bridge, "cmd_save_scene", {})

        # dry-run preview: lists the referencing files, moves nothing.
        preview = await _ok(
            bridge,
            "cmd_move_resource_file",
            {"path": OLD_SCRIPT, "new_path": NEW_SCRIPT, "preview": True},
        )
        assert preview["moved"] is False
        assert preview["undoable"] is False
        ref_files = [r["file"] for r in preview["updated_refs"]]
        assert preview["moved"] is False
        assert preview["undoable"] is False
        ref_files = [r["file"] for r in preview["updated_refs"]]
        assert REF_SCENE in ref_files

        # real move: the file lands, the referencing scene is rewritten.
        result = await _ok(
            bridge,
            "cmd_move_resource_file",
            {"path": OLD_SCRIPT, "new_path": NEW_SCRIPT},
        )
        assert result["moved"] is True and result["undoable"] is False
        assert result["old_path"] == OLD_SCRIPT and result["new_path"] == NEW_SCRIPT
        moved_refs = [r for r in result["updated_refs"] if r["file"] == REF_SCENE]
        assert moved_refs and moved_refs[0]["count"] >= 1
        # The old path is gone, the new file exists, the scene references the new path.
        gone = await bridge.send("cmd_path_to_uid", {"path": OLD_SCRIPT})
        assert not gone.ok  # no resource at the old path anymore
        scene_text = (GODOT_PROJECT / "tmp_e2e_moved_ref.tscn").read_text()
        assert NEW_SCRIPT in scene_text and OLD_SCRIPT not in scene_text

        # Unsaved-scene refusal: edit the open scene, then try to move it.
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node", "name": "Extra"}
        )
        dirty = await bridge.send(
            "cmd_move_resource_file", {"path": REF_SCENE, "new_path": "res://tmp_e2e_moved_ref2.tscn"}
        )
        assert not dirty.ok and dirty.error == "PRECONDITION_FAILED"
        assert "unsaved" in str(dirty.hint)

        # destination-exists refusal is structured
        dup = await bridge.send(
            "cmd_move_resource_file", {"path": REF_SCENE, "new_path": NEW_SCRIPT}
        )
        assert not dup.ok and dup.error == "VALIDATION_ERROR"
        assert "already exists" in str(dup.hint)

        await _ok(bridge, "cmd_close_scene", {"confirm": True, "scene_path": REF_SCENE})
    finally:
        await bridge.close()


def test_live_move_resource_file() -> None:
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
        for f in FILES:
            f.unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)