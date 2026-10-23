"""End-to-end script tools test: live editor + real parse check (issue #10).

Drives the addon script handlers over the bridge (write/read/patch, with UndoRedo +
filesystem rescan) against a live editor, and validates structured parse errors via
a real ``godot --check-only`` run. Skipped without Godot.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.runtime import GodotRunner
from mcp_server.scripts_parse import parse_check_errors
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
VALID = "res://tmp_e2e_script.gd"
BROKEN = "res://tmp_e2e_broken.gd"
SCENE = "res://tmp_e2e_scene.tscn"
_ARTIFACTS = [
    "tmp_e2e_script.gd",
    "tmp_e2e_script.gd.uid",
    "tmp_e2e_broken.gd",
    "tmp_e2e_broken.gd.uid",
    "tmp_e2e_scene.tscn",
]


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

    runner = GodotRunner(ServerConfig(godot_bin=GODOT_BIN))
    try:
        # write → read round-trip
        written = await _ok(
            bridge,
            "cmd_write_script",
            {"script_path": VALID, "content": 'extends Node\nfunc _ready():\n\tprint("hi")\n'},
        )
        assert written["created"] is True
        assert written["receipt"]["status"] == "created"
        assert written["receipt"]["changes"][0]["op"] == "write"
        read = await _ok(bridge, "cmd_read_script", {"script_path": VALID})
        assert 'print("hi")' in read["content"]

        # patch
        patched = await _ok(
            bridge, "cmd_patch_script", {"script_path": VALID, "find": "hi", "replace": "bye"}
        )
        assert patched["replacements"] == 1
        assert patched["receipt"]["status"] == "updated"
        after = await _ok(bridge, "cmd_read_script", {"script_path": VALID})
        assert 'print("bye")' in after["content"]

        # the valid (patched) script parses cleanly
        good = await runner.check_script(str(GODOT_PROJECT), VALID, timeout=60.0)
        assert parse_check_errors(good.stdout + "\n" + good.stderr) == []

        # get_script_for_node reports the resolved scene-relative path + attached script
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCENE})
        for _ in range(40):
            opened = await bridge.send("cmd_get_active_scene")
            if opened.ok and (opened.result or {}).get("is_open"):
                break
            await asyncio.sleep(0.25)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node", "name": "Probe"}
        )
        await _ok(bridge, "cmd_attach_script", {"node_path": "Probe", "script_path": VALID})
        for_node = await _ok(bridge, "cmd_get_script_for_node", {"node_path": "Probe"})
        assert for_node["node_path"] == "Probe"  # resolved path, not the empty input
        assert for_node["script_path"] == VALID

        # a broken script yields a structured parse error with a line number
        broken_src = "extends Node\nvar x =\n"
        await _ok(bridge, "cmd_write_script", {"script_path": BROKEN, "content": broken_src})
        bad = await runner.check_script(str(GODOT_PROJECT), BROKEN, timeout=60.0)
        errors = parse_check_errors(bad.stdout + "\n" + bad.stderr)
        assert errors and errors[0].line is not None
    finally:
        await bridge.close()


def test_live_script_workflow() -> None:
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
        for name in _ARTIFACTS:
            (GODOT_PROJECT / name).unlink(missing_ok=True)


# #640: a script write with a scene open must land in the scene history, so
# godot_undo reverts the script (not an earlier node edit) and the dock's
# "Last action" reflects it.
UNDO_SCRIPT = "res://tmp_e2e_undo_script.gd"
UNDO_SCENE = "res://tmp_e2e_undo_scene.tscn"


async def _run_script_undo() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": UNDO_SCENE})
        for _ in range(40):
            opened = await bridge.send("cmd_get_active_scene")
            if opened.ok and (opened.result or {}).get("is_open"):
                break
            await asyncio.sleep(0.25)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node2D", "name": "Box"}
        )
        await _ok(
            bridge, "cmd_write_script", {"script_path": UNDO_SCRIPT, "content": "extends Node\n"}
        )

        # Acceptance 2: the scene history (the dock's "Last action" view) names the
        # script write — proving it did NOT land in the global history (#640).
        history = await _ok(bridge, "cmd_list_history", {})
        assert str(history["current_action"]).startswith("Write script"), history["current_action"]

        # Acceptance 1: undo reverts the SCRIPT, not the earlier node create.
        await _ok(bridge, "cmd_undo", {})
        assert not (GODOT_PROJECT / "tmp_e2e_undo_script.gd").exists(), (
            "undo did not revert the script write (#640)"
        )
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        assert any(c["name"] == "Box" for c in tree["tree"]["children"]), (
            "undo reverted the node create instead of the script write (#640)"
        )
    finally:
        await bridge.close()


def test_live_script_undo_targets_the_script() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_script_undo())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        for name in (
            "tmp_e2e_undo_script.gd",
            "tmp_e2e_undo_script.gd.uid",
            "tmp_e2e_undo_scene.tscn",
            "tmp_e2e_undo_scene.tscn.uid",
        ):
            (GODOT_PROJECT / name).unlink(missing_ok=True)
