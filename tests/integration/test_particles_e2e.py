"""End-to-end particle test against a live editor (issue #42)."""

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
SCRATCH = "res://tmp_e2e_particles.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_particles.tscn"


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

        created = await _ok(
            bridge,
            "cmd_create_particles",
            {
                "parent_path": ".",
                "particles_type": "GPUParticles2D",
                "name": "FX",
                "amount": 32,
                "lifetime": 2.0,
                "properties": {"one_shot": True},
            },
        )
        assert created["node_path"] == "FX" and created["created"] is True
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        fx = next(c for c in tree["tree"]["children"] if c["name"] == "FX")
        assert fx["type"] == "GPUParticles2D"

        mat = await _ok(
            bridge,
            "cmd_set_particle_material",
            # orbit_velocity_min round-trips through the editor's property list;
            # initial_velocity_* are settable but the editor renderer omits them from
            # the read (a Godot editor-vs-headless property-exposure quirk, see #263).
            {"node_path": "FX", "properties": {"spread": 33.0, "orbit_velocity_min": 25.0}},
        )
        assert mat["properties"]["spread"] == 33.0

        grad = await _ok(
            bridge,
            "cmd_set_particle_color_gradient",
            {"node_path": "FX", "colors": ["#ffee88", "#ff6600", "#00000000"]},
        )
        assert grad["stops"] == 3

        # P4 (#219): read the material back — the props + the 3-stop ramp just set.
        read = await _ok(bridge, "cmd_get_particle_material", {"node_path": "FX"})
        assert read["has_material"] is True
        assert read["properties"]["spread"] == 33.0
        assert read["properties"]["orbit_velocity_min"] == 25.0
        assert read["color_ramp"] is not None
        assert len(read["color_ramp"]["offsets"]) == 3 and len(read["color_ramp"]["colors"]) == 3

        preset = await _ok(
            bridge, "cmd_apply_particle_preset", {"node_path": "FX", "preset": "explosion"}
        )
        assert preset["preset"] == "explosion"

        # validation: non-particle target, bad node type, unknown preset, empty colors
        await _create(bridge, "Plain", "Node2D")
        not_particles = await bridge.send(
            "cmd_set_particle_material", {"node_path": "Plain", "properties": {}}
        )
        assert not_particles.ok is False and not_particles.error == "VALIDATION_ERROR"
        bad_type = await bridge.send(
            "cmd_create_particles", {"parent_path": ".", "particles_type": "Node2D"}
        )
        assert bad_type.ok is False and bad_type.error == "VALIDATION_ERROR"
        bad_preset = await bridge.send(
            "cmd_apply_particle_preset", {"node_path": "FX", "preset": "nope"}
        )
        assert bad_preset.ok is False and bad_preset.error == "VALIDATION_ERROR"
        empty_colors = await bridge.send(
            "cmd_set_particle_color_gradient", {"node_path": "FX", "colors": []}
        )
        assert empty_colors.ok is False and empty_colors.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_particles() -> None:
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
