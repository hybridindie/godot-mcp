"""End-to-end mutation test: live Python bridge ↔ live Godot editor (issue #6).

Boots the headless editor and drives a full mutation roundtrip — create a scene,
add a node, set a property, rename, save, and delete (with/without confirm) —
against the real EditorInterface + EditorUndoRedoManager. This is the acceptance
test "all mutation tools work on a live Godot scene". Skipped without Godot.
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
SCRATCH = "res://e2e_scratch.tscn"
SCRATCH_FILE = GODOT_PROJECT / "e2e_scratch.tscn"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await bridge.send(command, params or {})
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _run_roundtrip() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await wait_for_active_scene(bridge)

        created = await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Sprite2D", "name": "Hero"}
        )
        assert created["created"] is True and created["node_path"] == "Hero"
        assert created["receipt"]["status"] == "created"
        assert created["receipt"]["changes"][0]["op"] == "add"
        assert created["receipt"]["changes"][0]["path"] == "Hero"

        was_set = await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Hero", "property": "position", "value": {"x": 10, "y": 20}},
        )
        assert was_set["value"] == {"x": 10.0, "y": 20.0}  # coerced JSON → Vector2 → JSON
        assert was_set["receipt"]["status"] == "updated"
        assert was_set["receipt"]["changes"][0]["op"] == "set"
        assert was_set["receipt"]["changes"][0]["before"] == {"x": 0.0, "y": 0.0}
        assert was_set["receipt"]["changes"][0]["after"] == {"x": 10.0, "y": 20.0}

        # Agent-friendly string form is also coerced (issue #51).
        as_string = await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Hero", "property": "position", "value": "Vector2(30, 40)"},
        )
        assert as_string["value"] == {"x": 30.0, "y": 40.0}
        # Idempotent re-run: the target already matches the request.
        again = await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Hero", "property": "position", "value": "Vector2(30, 40)"},
        )
        assert again["receipt"]["status"] == "existed"
        assert again["receipt"]["changes"] == []

        renamed = await _ok(bridge, "cmd_rename_node", {"node_path": "Hero", "new_name": "Player"})
        assert renamed["new_name"] == "Player"
        assert renamed["receipt"]["changes"][0]["op"] == "rename"
        assert renamed["receipt"]["changes"][0]["before"] == "Hero"
        assert renamed["receipt"]["changes"][0]["after"] == "Player"

        tree = await _ok(bridge, "cmd_get_scene_tree")
        names = [c["name"] for c in tree["tree"]["children"]]
        assert "Player" in names and "Hero" not in names

        saved = await _ok(bridge, "cmd_save_scene")
        assert saved["saved"] is True and saved["path"] == SCRATCH

        # Destructive guard is honored addon-side too.
        blocked = await bridge.send("cmd_delete_node", {"node_path": "Player", "confirm": False})
        assert blocked.ok is False and blocked.required == "confirm"

        deleted = await _ok(bridge, "cmd_delete_node", {"node_path": "Player", "confirm": True})
        assert deleted["deleted"] is True
        assert deleted["receipt"]["changes"][0]["op"] == "remove"
        assert deleted["receipt"]["changes"][0]["path"] == "Player"

        after = await _ok(bridge, "cmd_get_scene_tree")
        assert "Player" not in [c["name"] for c in after["tree"]["children"]]
    finally:
        await bridge.close()


# #414: a res:// path for an Object-typed property must be coerced via load(),
# and a failed/absent assignment must never report set:true.
async def _run_object_property_coercion() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    scratch = "res://e2e_obj_prop.tscn"
    scratch_file = GODOT_PROJECT / "e2e_obj_prop.tscn"
    mat_path = GODOT_PROJECT / "e2e_obj_prop_mat.tres"
    mat_code = (
        "[gd_resource type=\"StandardMaterial3D\" format=3]\n"
        "[resource]\n"
        "resource_name = \"e2e_mat\"\n"
        "albedo_color = Color(1, 0, 0, 1)\n"
    )
    try:
        mat_path.write_text(mat_code, encoding="utf-8")
        created = await _ok(
            bridge,
            "cmd_create_scene",
            {"root_type": "MeshInstance3D", "scene_path": scratch},
        )
        assert created["created"] is True
        await wait_for_active_scene(bridge)

        # Happy path: res:// path coerces via load() for the Object property.
        was_set = await _ok(
            bridge,
            "cmd_set_node_property",
            {
                "node_path": ".",
                "property": "material_override",
                "value": "res://e2e_obj_prop_mat.tres",
            },
        )
        assert was_set["set"] is True
        assert was_set["value"] == "res://e2e_obj_prop_mat.tres", (
            f"material_override did not land (echo={was_set['value']})"
        )

        # A nonexistent res:// path must fail, not silently set null.
        bad = await bridge.send(
            "cmd_set_node_property",
            {
                "node_path": ".",
                "property": "material_override",
                "value": "res://no_such_material.tres",
            },
        )
        assert bad.ok is False and bad.error == "RESOURCE_NOT_FOUND", (
            f"missing path silently set: {bad.error} {bad.hint}"
        )
        cleared = await _ok(
            bridge, "cmd_get_node_property", {"node_path": ".", "property": "material_override"}
        )
        assert cleared["value"] in (None, "res://e2e_obj_prop_mat.tres")
    finally:
        await bridge.close()
        scratch_file.unlink(missing_ok=True)
        (GODOT_PROJECT / "e2e_obj_prop_mat.tres").unlink(missing_ok=True)
        (GODOT_PROJECT / "e2e_obj_prop_mat.tres.uid").unlink(missing_ok=True)


def test_live_editor_set_node_property_object_coercion() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_object_property_coercion())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()


def test_live_editor_mutation_roundtrip() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_roundtrip())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        SCRATCH_FILE.unlink(missing_ok=True)


async def _run_nested_dir() -> None:
    # #412: create_scene into a not-yet-existing directory must auto-create the
    # parent (parity with _write_file_text) instead of failing with an opaque
    # ResourceSaver "error 19". Also pins the actionable error if creation is
    # impossible for another reason.
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    nested = "res://e2e_scratch_dir/deep/created.tscn"
    nested_file = GODOT_PROJECT / "e2e_scratch_dir" / "deep" / "created.tscn"
    try:
        result = await _ok(
            bridge,
            "cmd_create_scene",
            {"root_type": "Node2D", "scene_path": nested},
        )
        assert result["created"] is True and result["scene_path"] == nested
        assert nested_file.exists(), "parent dirs were not created"
        opened = await bridge.send("cmd_get_active_scene")
        assert opened.ok and (opened.result or {}).get("is_open")
    finally:
        await bridge.close()


def test_live_editor_create_scene_creates_parent_dirs() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_nested_dir())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        nested_file = GODOT_PROJECT / "e2e_scratch_dir"
        if nested_file.exists():
            import shutil

            shutil.rmtree(nested_file)
