"""End-to-end extract-scene test against a live editor (issue #531).

Builds a scene with a subtree, extracts it into a .tscn prefab (with and without
replace_with_instance), and verifies the refusal for an instanced (non-owned)
subtree — the #477 honesty rule.
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
SCRATCH = "res://tmp_e2e_extract_host.tscn"
SCRATCH_PREFAB = "res://tmp_e2e_extract_prefab.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_extract_host.tscn"
PREFAB_FILE = GODOT_PROJECT / "tmp_e2e_extract_prefab.tscn"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"


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
        # Host scene with a Gun subtree: Gun/Barrel/Muzzle + a property.
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "name": "Gun"},
        )
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": "Gun", "node_type": "Node2D", "name": "Barrel"},
        )
        await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Gun/Barrel", "property": "position", "value": {"x": 3, "y": 4}},
        )
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": "Gun/Barrel", "node_type": "Node2D", "name": "Tip"},
        )
        await _ok(bridge, "cmd_save_scene", {})

        # dry-run preview: nothing written, node list reported.
        preview = await _ok(
            bridge,
            "cmd_extract_scene",
            {"node_path": "Gun", "scene_path": SCRATCH_PREFAB, "preview": True},
        )
        assert preview["extracted"] is False
        assert preview["node_count"] == 3
        assert not PREFAB_FILE.exists()

        # real extract (no replace): the .tscn lands on disk, host tree untouched.
        result = await _ok(
            bridge,
            "cmd_extract_scene",
            {"node_path": "Gun", "scene_path": SCRATCH_PREFAB},
        )
        assert result["extracted"] is True and result["replaced"] is False
        assert result["node_count"] == 3
        assert PREFAB_FILE.exists()

        # second extract with replace_with_instance: subtree becomes an instance.
        SCRATCH2 = "res://tmp_e2e_extract_host2.tscn"
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH2})
        await _wait_scene_open(bridge)
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "name": "Gun"},
        )
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": "Gun", "node_type": "Node2D", "name": "Barrel"},
        )
        await _ok(bridge, "cmd_save_scene", {})

        # destination-exists refusal is structured
        dup = await bridge.send(
            "cmd_extract_scene", {"node_path": "Gun", "scene_path": SCRATCH_PREFAB}
        )
        assert not dup.ok and dup.error == "VALIDATION_ERROR" and "already exists" in str(dup.hint)

        replaced = await _ok(
            bridge,
            "cmd_extract_scene",
            {
                "node_path": "Gun",
                "scene_path": SCRATCH2.replace(".tscn", "_prefab.tscn"),
                "replace_with_instance": True,
            },
        )
        assert replaced["replaced"] is True
        assert replaced["instance_path"] == "Gun"
        # The replaced node is now an instance of the prefab: its owner differs
        # from the edited root (it belongs to the prefab scene) — visible in the
        # scene tree's instance metadata (#487).
        tree = await _ok(bridge, "cmd_get_scene_tree", {"max_depth": 2})

        def _find(tree_node: dict[str, Any], name: str) -> dict[str, Any] | None:
            if tree_node.get("name") == name:
                return tree_node
            for child in tree_node.get("children", []):
                found = _find(child, name)
                if found is not None:
                    return found
            return None
        gun = _find(tree["tree"], "Gun")
        assert gun is not None
        # The instance root stays owned by the edited root (the packer stores the
        # instance entry + overrides); its children belong to the prefab scene.
        barrel = _find(tree["tree"], "Barrel")
        assert barrel is not None
        assert barrel.get("owner") == SCRATCH2.replace(".tscn", "_prefab.tscn")

        # #477 honesty: extracting inside a non-editable instanced child is refused.
        await _ok(
            bridge,
            "cmd_instance_scene",
            {"parent_path": ".", "scene_path": SCRATCH_PREFAB, "name": "Prefab"},
        )
        inside = await bridge.send(
            "cmd_extract_scene",
            {"node_path": "Prefab/Barrel", "scene_path": "res://tmp_e2e_extract_inside.tscn"},
        )
        assert not inside.ok and inside.error == "VALIDATION_ERROR"
        assert "Editable Children" in str(inside.hint)
        (GODOT_PROJECT / "tmp_e2e_extract_inside.tscn").unlink(missing_ok=True)

        await _ok(bridge, "cmd_close_scene", {"confirm": True, "scene_path": SCRATCH2})
    finally:
        await bridge.close()


def test_live_extract_scene() -> None:
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
        PREFAB_FILE.unlink(missing_ok=True)
        (GODOT_PROJECT / "tmp_e2e_extract_host2.tscn").unlink(missing_ok=True)
        (GODOT_PROJECT / "tmp_e2e_extract_host2_prefab.tscn").unlink(missing_ok=True)
        SCRATCH_FILE.unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)