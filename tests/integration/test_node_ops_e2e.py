"""End-to-end node-parity test against a live editor (issue #31).

Exercises duplicate / move / group / signal list+disconnect via the bridge,
verifying through the scene tree and the connection list. Skipped without Godot.
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
SCRATCH = "res://tmp_e2e_nodeops.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_nodeops.tscn"


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
    finally:
        await bridge.close()


def test_live_node_parity() -> None:
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
