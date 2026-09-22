"""End-to-end composite-commit test against a live editor (issue #528).

Drives the shared N-child undo commit (``mcp_helpers.commit_add_children``)
through its three consumers: ``cmd_create_node`` (single), ``cmd_compose_node``
(subtree), and ``cmd_batch_create_nodes`` (flat batch). Asserts the nodes land
in the tree, a single ``cmd_undo`` reverts the WHOLE composite/batch (the
one-action contract), and ``cmd_redo`` (#529) restores it.
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
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_commit.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_commit.tscn"


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

        # Single-child create routes through the shared commit (one action).
        created = await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "name": "Solo"},
        )
        assert created["created"] is True and "Solo" in created["node_path"]

        # Flat batch create: three siblings in ONE undo action.
        batch = await _ok(
            bridge,
            "cmd_batch_create_nodes",
            {"parent_path": ".", "node_type": "Node2D", "names": ["B1", "B2", "B3"]},
        )
        assert batch["created"] == ["B1", "B2", "B3"] and batch["undoable"] is True

        # Compose: one node + two children, the subtree owned in one action.
        composed = await _ok(
            bridge,
            "cmd_compose_node",
            {
                "parent_path": ".",
                "node_type": "Node2D",
                "name": "Trunk",
                "children": [
                    {"node_type": "Node2D", "name": "LeafA"},
                    {"node_type": "Node2D", "name": "LeafB"},
                ],
            },
        )
        assert composed["children"] == ["LeafA", "LeafB"]

        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        names = _child_names(tree)
        for expected in ("Solo", "B1", "B2", "B3", "Trunk"):
            assert expected in names, f"{expected} missing after create: {names}"

        # ONE undo reverts the compose (whole subtree) — the one-action contract.
        undone = await _ok(bridge, "cmd_undo", {"count": 1})
        assert undone["undone"] == 1
        after_undo = await _ok(bridge, "cmd_get_scene_tree", {})
        assert "Trunk" not in _child_names(after_undo), "undo did not revert the compose"

        # #529: redo restores it.
        redone = await _ok(bridge, "cmd_redo", {"count": 1})
        assert redone["redone"] == 1
        after_redo = await _ok(bridge, "cmd_get_scene_tree", {})
        assert "Trunk" in _child_names(after_redo), "redo did not restore the compose"

        # The batch create is its own action: two undos pop compose + batch.
        await _ok(bridge, "cmd_undo", {"count": 2})
        after_undo2 = await _ok(bridge, "cmd_get_scene_tree", {})
        names2 = _child_names(after_undo2)
        for gone in ("B1", "B2", "B3", "Trunk"):
            assert gone not in names2, f"batch undo left {gone} behind"
        assert "Solo" in names2, "undo dropped the unrelated Solo node"
    finally:
        await bridge.close()


def test_live_composite_commit_is_one_undo_action() -> None:
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
        (GODOT_PROJECT / "tmp_e2e_commit.tscn.uid").unlink(missing_ok=True)