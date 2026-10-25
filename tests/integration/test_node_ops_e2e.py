"""End-to-end node-parity test against a live editor (issue #31).

Exercises duplicate / move / group / signal list+disconnect via the bridge,
verifying through the scene tree and the connection list. Skipped without Godot.
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
    serve_and_await_editor,
    wait_for_active_scene,
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# Ephemeral per-run port (issue #444): no fixed port, so a concurrent
# job's (or an orphaned) editor can never connect to this test's listener.
BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_nodeops.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_nodeops.tscn"
# #642: a reusable sub-scene (with a distinguishable internal node) and the main
# scene that instances + moves it.
SUB = "res://tmp_e2e_nodeops_sub.tscn"
SUB_FILE = GODOT_PROJECT / "tmp_e2e_nodeops_sub.tscn"
INST_SCENE = "res://tmp_e2e_nodeops_inst.tscn"
INST_SCENE_FILE = GODOT_PROJECT / "tmp_e2e_nodeops_inst.tscn"


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
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await wait_for_active_scene(bridge, SCRATCH)
        for name, node_type in (("Box", "Node2D"), ("Inner", "Node2D"), ("Clock", "Timer")):
            await _ok(
                bridge,
                "cmd_create_node",
                {"parent_path": ".", "node_type": node_type, "name": name},
            )

        # duplicate
        dup = await _ok(bridge, "cmd_duplicate_node", {"node_path": "Box"})
        assert dup["node_path"].startswith("Box") and dup["node_path"] != "Box"

        # move Inner under Box, verify via scene tree
        moved = await _ok(bridge, "cmd_move_node", {"node_path": "Inner", "new_parent_path": "Box"})
        assert moved["node_path"] == "Box/Inner"
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        box = next(c for c in tree["tree"]["children"] if c["name"] == "Box")
        assert any(child["name"] == "Inner" for child in box["children"])

        # groups
        added = await _ok(bridge, "cmd_add_to_group", {"node_path": "Box", "group": "obstacles"})
        assert added["added"] is True

        # connect a signal (existing tool), list it, disconnect it
        sig = {
            "source_path": "Clock",
            "signal_name": "timeout",
            "target_path": ".",
            "method_name": "queue_free",
        }
        await _ok(bridge, "cmd_connect_signal", sig)
        listed = await _ok(bridge, "cmd_list_signal_connections", {"node_path": "Clock"})
        assert any(
            c["signal"] == "timeout" and c["method"] == "queue_free" for c in listed["connections"]
        )
        disc = await _ok(bridge, "cmd_disconnect_signal", sig)
        assert disc["disconnected"] is True
        after = await _ok(bridge, "cmd_list_signal_connections", {"node_path": "Clock"})
        assert not any(
            c["signal"] == "timeout" and c["method"] == "queue_free" for c in after["connections"]
        )

        # Input validation: a typoed signal gives a specific error, not "not connected".
        bad_signal = {**sig, "signal_name": "no_such_signal"}
        bad = await bridge.send("cmd_disconnect_signal", bad_signal)
        assert bad.ok is False and "no_such_signal" in (bad.hint or "")
        empty_group = await bridge.send("cmd_remove_from_group", {"node_path": "Box", "group": ""})
        assert empty_group.ok is False and empty_group.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_node_parity() -> None:
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
        SCRATCH_FILE.unlink(missing_ok=True)


async def _run_instance_ownership() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # A reusable sub-scene with a distinguishable internal node.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SUB})
        await wait_for_active_scene(bridge, SUB)
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "name": "SubChild"},
        )
        await _ok(bridge, "cmd_save_scene", {})

        # The main scene instances the sub-scene, then moves the instance into a
        # holder — the move triggers own_recursive over the instance.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": INST_SCENE})
        await wait_for_active_scene(bridge, INST_SCENE)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node2D", "name": "Holder"}
        )
        await _ok(
            bridge,
            "cmd_instance_scene",
            {"parent_path": ".", "scene_path": SUB, "name": "Inst"},
        )
        await _ok(bridge, "cmd_move_node", {"node_path": "Inst", "new_parent_path": "Holder"})
        await _ok(bridge, "cmd_save_scene", {})

        saved = INST_SCENE_FILE.read_text()
        # #642: the instance's INTERNAL nodes must not be serialised as local nodes
        # (that duplicates/corrupts the instanced scene on reload). The sub-scene's
        # internal node name must not appear in the host scene at all.
        assert "SubChild" not in saved, (
            "instanced internals were serialised into the host scene (#642):\n" + saved
        )
        # Exactly one instance reference (the moved instance).
        assert saved.count("instance=") == 1, saved

        # Undo the move: ownership must return cleanly (still one instance, no
        # leaked internals) — the undo path calls own_recursive too.
        await _ok(bridge, "cmd_undo", {})
        await _ok(bridge, "cmd_save_scene", {})
        undone = INST_SCENE_FILE.read_text()
        assert "SubChild" not in undone, (
            "undo of move serialised instanced internals (#642):\n" + undone
        )
        assert undone.count("instance=") == 1, undone
    finally:
        await bridge.close()


def test_live_instance_ownership_preserved() -> None:
    """#642: duplicate/move must not rewrite ownership inside an instanced sub-scene."""
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_instance_ownership())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        for f in (SUB_FILE, INST_SCENE_FILE):
            f.unlink(missing_ok=True)
            f.with_name(f.name + ".uid").unlink(missing_ok=True)
