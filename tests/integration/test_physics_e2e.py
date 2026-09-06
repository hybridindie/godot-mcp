"""End-to-end physics test against a live editor (issue #41)."""

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

BRIDGE_URL = "ws://127.0.0.1:9097"
SCRATCH = "res://tmp_e2e_physics.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_physics.tscn"


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
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _create(bridge, "Body", "RigidBody2D")

        # collision shape under the body
        col = await _ok(
            bridge,
            "cmd_setup_collision",
            {
                "node_path": "Body",
                "shape_type": "RectangleShape2D",
                "properties": {"size": {"x": 32, "y": 48}},
            },
        )
        assert col["created"] is True
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        body = next(c for c in tree["tree"]["children"] if c["name"] == "Body")
        assert any(child["type"] == "CollisionShape2D" for child in body["children"])

        # layers/masks from bit indices
        layers = await _ok(
            bridge, "cmd_set_physics_layers", {"node_path": "Body", "layers": [1, 3], "mask": [2]}
        )
        assert layers["collision_layer"] == 5  # bits 1 and 3 → 1 | 4
        assert layers["collision_mask"] == 2  # bit 2

        # body properties (batch)
        body_props = await _ok(
            bridge,
            "cmd_setup_physics_body",
            {"node_path": "Body", "properties": {"mass": 7, "gravity_scale": 2}},
        )
        assert body_props["properties"]["mass"] == 7.0

        # raycast with a string-form Vector2
        ray = await _ok(
            bridge,
            "cmd_add_raycast",
            {
                "parent_path": ".",
                "name": "Ray",
                "properties": {"target_position": "Vector2(0, 120)"},
            },
        )
        assert ray["created"] is True

        # validation: non-physics target, wrong shape type, and bad bit arrays.
        await _create(bridge, "Plain", "Node")
        bad_layers = await bridge.send(
            "cmd_set_physics_layers", {"node_path": "Plain", "layers": [1]}
        )
        assert bad_layers.ok is False and bad_layers.error == "VALIDATION_ERROR"
        bad_collision = await bridge.send(
            "cmd_setup_collision", {"node_path": "Plain", "shape_type": "RectangleShape2D"}
        )
        assert bad_collision.ok is False and bad_collision.error == "VALIDATION_ERROR"
        bad_bits = await bridge.send(
            "cmd_set_physics_layers", {"node_path": "Body", "layers": "nope"}
        )
        assert bad_bits.ok is False and bad_bits.error == "VALIDATION_ERROR"
        bad_ray = await bridge.send(
            "cmd_add_raycast", {"parent_path": ".", "name": "X", "raycast_type": "Node2D"}
        )
        assert bad_ray.ok is False and bad_ray.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_physics() -> None:
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


async def _run_3d_dimension() -> None:
    # #410: setup_collision must not silently ship a collisionless 3D level.
    # (a) a BoxShape3D with the default (2D) collision node is a dimension
    #     mismatch -> structured VALIDATION_ERROR, nothing created;
    # (b) an explicit CollisionShape3D + BoxShape3D actually collides
    #     (shape lands on the node, ok:true is truthful).
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    scene = "res://e2e_physics3d_scratch.tscn"
    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node3D", "scene_path": scene})
        await _wait_scene_open(bridge)
        await _create(bridge, "FloorBody", "StaticBody3D")

        # (a) 3D shape + default 2D node -> dimension mismatch, rejected
        mismatch = await bridge.send(
            "cmd_setup_collision",
            {
                "node_path": "FloorBody",
                "shape_type": "BoxShape3D",
                "properties": {"size": [30, 1, 30]},
            },
        )
        assert mismatch.ok is False and mismatch.error == "VALIDATION_ERROR"
        assert mismatch.hint and "dimension" in mismatch.hint.lower()
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        floor_body = next(c for c in tree["tree"]["children"] if c["name"] == "FloorBody")
        assert not floor_body.get("children"), "no node may be created on a mismatch"

        # (a2) 2D shape under the 3D body is ALSO a mismatch (shape vs parent
        # body dimensions, the Qodo follow-up finding): even with a matching
        # 2D collision node, a RectangleShape2D on a StaticBody3D must fail —
        # a 2D shape can never collide in a 3D physics world.
        two_d = await bridge.send(
            "cmd_setup_collision",
            {
                "node_path": "FloorBody",
                "shape_type": "RectangleShape2D",
                "collision_node_type": "CollisionShape2D",
                "properties": {"size": [30, 1]},
            },
        )
        assert two_d.ok is False and two_d.error == "VALIDATION_ERROR"
        assert two_d.hint and "dimension" in two_d.hint.lower()
        tree2 = await _ok(bridge, "cmd_get_scene_tree", {})
        floor_body2 = next(c for c in tree2["tree"]["children"] if c["name"] == "FloorBody")
        assert not floor_body2.get("children"), "no node may be created on a 2D-under-3D mismatch"

        # (b) explicit 3D node + 3D shape -> shape really attached
        col = await _ok(
            bridge,
            "cmd_setup_collision",
            {
                "node_path": "FloorBody",
                "shape_type": "BoxShape3D",
                "collision_node_type": "CollisionShape3D",
                "properties": {"size": [30, 1, 30]},
            },
        )
        assert col["created"] is True
        col_path = str(col["node_path"])  # the addon echoes the real path
        shape_read = await _ok(
            bridge, "cmd_get_node_property", {"node_path": col_path, "property": "shape"}
        )
        assert shape_read["exists"] is True and shape_read["value"] is not None, (
            "shape silently dropped (the #410 symptom)"
        )
    finally:
        await bridge.close()


def test_live_physics_3d_dimension_mismatch() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_3d_dimension())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        (GODOT_PROJECT / "e2e_physics3d_scratch.tscn").unlink(missing_ok=True)
