"""End-to-end rename refusal test: live Python bridge ↔ live Godot editor (#473).

The editor refuses renames the old addon allowed, and both refused kinds
corrupt the save: renaming an instanced child is dropped on save; renaming a
node an inherited scene gets from its base *duplicates* the node. This pins
the refusals live (error + no change) and the still-allowed set (scene-owned
node, instance root, edited root — each surviving save + reload).
Skipped without Godot.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
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

# Ephemeral per-run port (issue #444): no fixed port, so a concurrent
# job's (or an orphaned) editor can never connect to this test's listener.
BRIDGE_URL = e2e_bridge_url()

BASE = "res://tmp_rename_refusal_base.tscn"
DERIVED = "res://tmp_rename_refusal_derived.tscn"
MAIN = "res://tmp_rename_refusal_main.tscn"

BASE_FILE = GODOT_PROJECT / "tmp_rename_refusal_base.tscn"
DERIVED_FILE = GODOT_PROJECT / "tmp_rename_refusal_derived.tscn"
MAIN_FILE = GODOT_PROJECT / "tmp_rename_refusal_main.tscn"
CLEANUP = [BASE_FILE, DERIVED_FILE, MAIN_FILE]

# main.tscn instances base.tscn twice: Relic (no Editable Children), Relic2 (with),
# per the #458/#473 fixture pattern.
MAIN_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://tmp_rename_refusal_base.tscn" id="1"]

[node name="Main" type="Node2D"]

[node name="Relic" parent="." instance=ExtResource("1")]

[node name="Relic2" parent="." instance=ExtResource("1")]
editable_path = NodePath("Relic2")
"""

BASE_TSCN = """[gd_scene format=3]

[node name="Base" type="Node2D"]

[node name="Cold" type="Node" parent="."]
"""

DERIVED_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" path="res://tmp_rename_refusal_base.tscn" id="1"]

[node name="Derived" instance=ExtResource("1")]
"""


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


def _write_fixtures() -> None:
    BASE_FILE.write_text(BASE_TSCN)
    DERIVED_FILE.write_text(DERIVED_TSCN)
    MAIN_FILE.write_text(MAIN_TSCN)


async def _run() -> None:
    _write_fixtures()
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        # --- Case 1: instanced child (editable and not) is refused, name survives reload.
        await _ok(bridge, "cmd_open_scene", {"scene_path": MAIN})
        refused = await bridge.send(
            "cmd_rename_node", {"node_path": "Relic/Cold", "new_name": "Warm"}
        )
        assert refused.ok is False and refused.error == "VALIDATION_ERROR", refused
        hint = refused.hint or ""
        assert "tmp_rename_refusal_base" in hint, hint  # names the source scene
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        assert "Cold" in str(tree) and "Warm" not in str(tree)
        refused_editable = await bridge.send(
            "cmd_rename_node", {"node_path": "Relic2/Cold", "new_name": "Warm"}
        )
        assert refused_editable.ok is False and refused_editable.error == "VALIDATION_ERROR"
        await _ok(bridge, "cmd_save_scene", {})
        saved = MAIN_FILE.read_text()
        assert "Warm" not in saved, saved

        # --- Case 2: a node an inherited scene gets from its base is refused.
        await _ok(bridge, "cmd_open_scene", {"scene_path": DERIVED})
        refused_base = await bridge.send(
            "cmd_rename_node", {"node_path": "Cold", "new_name": "Warm"}
        )
        assert refused_base.ok is False and refused_base.error == "VALIDATION_ERROR", refused_base
        hint_base = refused_base.hint or ""
        assert "base scene" in hint_base, hint_base
        await _ok(bridge, "cmd_save_scene", {})
        saved_derived = DERIVED_FILE.read_text()
        assert 'name="Warm"' not in saved_derived, saved_derived  # no duplicate packed

        # --- Case 3: the allowed set still renames and the rename survives a reload.
        # 3a: the edited root of the inherited scene.
        root_rename = await _ok(
            bridge, "cmd_rename_node", {"node_path": ".", "new_name": "DerivedRoot"}
        )
        assert root_rename["renamed"] is True, root_rename
        # 3b: a node the edited scene owns (created live, owner == root).
        created = await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Node2D", "name": "Owned"}
        )
        assert created["created"] is True
        # The edited root is back to its original name (still renamable either way).
        allowed = await _ok(
            bridge, "cmd_rename_node", {"node_path": ".", "new_name": "Derived"}
        )
        assert allowed["renamed"] is True and allowed["persisted"] is True, allowed
        allowed_owned = await _ok(
            bridge, "cmd_rename_node", {"node_path": "Owned", "new_name": "RenamedOwned"}
        )
        assert (
            allowed_owned["renamed"] is True and allowed_owned["persisted"] is True
        ), allowed_owned
        # Rename it back so the saved fixture matches the scene the reload asserts.
        await _ok(bridge, "cmd_rename_node", {"node_path": "RenamedOwned", "new_name": "Owned"})
        await _ok(bridge, "cmd_save_scene", {})
        reloaded = await _ok(bridge, "cmd_open_scene", {"scene_path": DERIVED})
        assert reloaded.get("is_open", True) is True
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        # The rename survived save + reload: the root kept its live name and the
        # base's Cold came through by its original name (no duplicate node).
        assert str(tree["tree"].get("name")) == "Derived", tree
        names = [c["name"] for c in tree["tree"].get("children", [])]
        assert names == ["Cold", "Owned"], names  # no duplicated/lost node
    finally:
        await bridge.close()
        for path in CLEANUP:
            path.unlink(missing_ok=True)
            Path(str(path) + ".uid").unlink(missing_ok=True)


def test_live_editor_rename_refusal() -> None:
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
        for path in CLEANUP:
            path.unlink(missing_ok=True)
            Path(str(path) + ".uid").unlink(missing_ok=True)