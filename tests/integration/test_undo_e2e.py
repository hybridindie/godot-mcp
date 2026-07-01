"""End-to-end undo smoke against a live editor (S4).

Drives a single ``run_commands`` batch (create a uniquely-named child) then
``cmd_undo``, asserting the node existed after creation and is gone after the
undo, with ``undone == 1``. Skipped without a Godot binary (CI has no editor) —
the one conditional skip the testing rules permit.
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

BRIDGE_URL = "ws://127.0.0.1:9098"
SCRATCH = "res://tmp_e2e_undo.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_undo.tscn"
TARGET = "UndoProbe"


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


def _child_names(tree: dict[str, Any]) -> list[str]:
    root = tree.get("tree") or {}
    return [c["name"] for c in root.get("children", [])]


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # Create the probe node in one batch, then verify it exists in the tree.
        await _ok(
            bridge,
            "cmd_run_commands",
            {
                "commands": [
                    {
                        "command": "cmd_create_node",
                        "params": {"parent_path": ".", "node_type": "Node2D", "name": TARGET},
                    }
                ]
            },
        )
        before = await _ok(bridge, "cmd_get_scene_tree", {})
        assert TARGET in _child_names(before), "probe node was not created"

        # Undo the create, then assert the node is gone and exactly one action popped.
        undone = await _ok(bridge, "cmd_undo", {"count": 1})
        assert undone["undone"] == 1, undone
        after = await _ok(bridge, "cmd_get_scene_tree", {})
        assert TARGET not in _child_names(after), "undo did not revert the create"
    finally:
        await bridge.close()


def test_live_undo_reverts_create() -> None:
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
