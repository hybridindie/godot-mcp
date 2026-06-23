"""End-to-end 3D scene test against a live editor (issues #40, #83).

Covers mesh/camera/light/environment + GridMap guards, then the MeshLibrary authoring
chain from #83 (create_mesh_library → add_mesh_library_item) — which finally lets
gridmap_set_cell place a real item. Primitive meshes need no asset; a BoxMesh saved as
a ``.tres`` exercises the ``mesh_path`` + file-backed-library path.
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
SCRATCH = "res://tmp_e2e_scene_3d.tscn"
MESH = "res://tmp_e2e_box.tres"
MESHLIB = "res://tmp_e2e_meshlib.tres"
MESHLIB_FILE = GODOT_PROJECT / "tmp_e2e_meshlib.tres"
# Scene + .tres resources and their Godot 4.4 .uid sidecars, all cleaned up after the run.
_ARTIFACTS = [
    "tmp_e2e_scene_3d.tscn",
    "tmp_e2e_scene_3d.tscn.uid",
    "tmp_e2e_box.tres",
    "tmp_e2e_box.tres.uid",
    "tmp_e2e_meshlib.tres",
    "tmp_e2e_meshlib.tres.uid",
]


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _create(bridge: Bridge, name: str, node_type: str, parent: str = ".") -> None:
    await _ok(
        bridge, "cmd_create_node", {"parent_path": parent, "node_type": node_type, "name": name}
    )


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
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node3D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        mesh = await _ok(
            bridge,
            "cmd_add_mesh_instance",
            {
                "parent_path": ".",
                "mesh_type": "SphereMesh",
                "name": "Ball",
                "properties": {"radius": 2.0},
            },
        )
        assert mesh["node_path"] == "Ball" and mesh["mesh_type"] == "SphereMesh"
        cam = await _ok(
            bridge,
            "cmd_setup_camera",
            {"parent_path": ".", "name": "Cam", "make_current": True, "properties": {"fov": 60}},
        )
        assert cam["current"] is True
        light = await _ok(
            bridge,
            "cmd_setup_lighting",
            {
                "parent_path": ".",
                "light_type": "OmniLight3D",
                "name": "Lamp",
                "properties": {"light_energy": 2.0},
            },
        )
        assert light["light_type"] == "OmniLight3D"
        env = await _ok(
            bridge,
            "cmd_setup_environment",
            {"parent_path": ".", "name": "World", "properties": {"ambient_light_energy": 0.5}},
        )
        assert env["created"] is True

        # confirm the nodes exist with the right types in the live tree
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        by_name = {c["name"]: c["type"] for c in tree["tree"]["children"]}
        assert by_name["Ball"] == "MeshInstance3D"
        assert by_name["Cam"] == "Camera3D"
        assert by_name["Lamp"] == "OmniLight3D"
        assert by_name["World"] == "WorldEnvironment"

        # GridMap cell needs a mesh_library: without one we return a structured guard
        await _create(bridge, "Grid", "GridMap")
        no_lib = await bridge.send(
            "cmd_gridmap_set_cell", {"node_path": "Grid", "position": [0, 0, 0], "item": 0}
        )
        assert no_lib.ok is False and no_lib.error == "VALIDATION_ERROR"
        assert no_lib.required == "mesh_library"

        # G5 (#219): reading a cell needs no mesh_library — an unset cell is empty/-1.
        empty_cell = await _ok(
            bridge, "cmd_gridmap_get_cell", {"node_path": "Grid", "position": [0, 0, 0]}
        )
        assert empty_cell["item"] == -1 and empty_cell["empty"] is True
        assert empty_cell["position"] == [0, 0, 0]

        # validation: bad mesh/light types, non-GridMap target, malformed position
        bad_mesh = await bridge.send(
            "cmd_add_mesh_instance", {"parent_path": ".", "mesh_type": "Node"}
        )
        assert bad_mesh.ok is False and bad_mesh.error == "VALIDATION_ERROR"
        bad_light = await bridge.send(
            "cmd_setup_lighting", {"parent_path": ".", "light_type": "Node3D"}
        )
        assert bad_light.ok is False and bad_light.error == "VALIDATION_ERROR"
        not_grid = await bridge.send(
            "cmd_gridmap_set_cell", {"node_path": "Ball", "position": [0, 0, 0], "item": 0}
        )
        assert not_grid.ok is False and not_grid.error == "VALIDATION_ERROR"
        bad_pos = await bridge.send(
            "cmd_gridmap_set_cell", {"node_path": "Grid", "position": [0, 0], "item": 0}
        )
        assert bad_pos.ok is False and bad_pos.error == "VALIDATION_ERROR"

        # --- MeshLibrary authoring (issue #83): build a library and place a REAL cell ---
        # node-backed: create the library on the GridMap, add primitive items
        lib = await _ok(bridge, "cmd_create_mesh_library", {"node_path": "Grid"})
        assert lib["created"] is True
        item0 = await _ok(
            bridge,
            "cmd_add_mesh_library_item",
            {"node_path": "Grid", "mesh_type": "BoxMesh", "name": "Block"},
        )
        assert item0["item_id"] == 0 and item0["name"] == "Block"
        # a second item auto-advances the id — proof item 0 was registered in the library
        item1 = await _ok(
            bridge, "cmd_add_mesh_library_item", {"node_path": "Grid", "mesh_type": "SphereMesh"}
        )
        assert item1["item_id"] == 1
        # reusing an existing id is rejected (further proof the item persisted)
        dup = await bridge.send(
            "cmd_add_mesh_library_item",
            {"node_path": "Grid", "mesh_type": "BoxMesh", "item_id": 0},
        )
        assert dup.ok is False and dup.error == "VALIDATION_ERROR"
        # the payoff: gridmap_set_cell now succeeds against a real library + item
        placed = await _ok(
            bridge, "cmd_gridmap_set_cell", {"node_path": "Grid", "position": [1, 0, 1], "item": 0}
        )
        assert placed["item"] == 0

        # file-backed: a MeshLibrary saved as .tres, item sourced from a Mesh .tres
        await _ok(bridge, "cmd_create_resource", {"type": "BoxMesh", "resource_path": MESH})
        saved = await _ok(bridge, "cmd_create_mesh_library", {"save_path": MESHLIB})
        assert saved["library_path"] == MESHLIB and MESHLIB_FILE.exists()
        fitem = await _ok(
            bridge,
            "cmd_add_mesh_library_item",
            {"library_path": MESHLIB, "mesh_path": MESH, "name": "Crate"},
        )
        assert fitem["item_id"] == 0 and fitem["mesh_path"] == MESH

        # validation: ambiguous target, ambiguous mesh source, and a non-Mesh mesh_path
        both_t = await bridge.send(
            "cmd_add_mesh_library_item",
            {"node_path": "Grid", "library_path": MESHLIB, "mesh_type": "BoxMesh"},
        )
        assert both_t.ok is False and both_t.error == "VALIDATION_ERROR"
        both_m = await bridge.send(
            "cmd_add_mesh_library_item",
            {"node_path": "Grid", "mesh_type": "BoxMesh", "mesh_path": MESH},
        )
        assert both_m.ok is False and both_m.error == "VALIDATION_ERROR"
        not_mesh = await bridge.send(
            "cmd_add_mesh_library_item", {"library_path": MESHLIB, "mesh_path": MESHLIB}
        )
        assert not_mesh.ok is False and not_mesh.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_scene_3d() -> None:
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
        for artifact in _ARTIFACTS:
            (GODOT_PROJECT / artifact).unlink(missing_ok=True)
