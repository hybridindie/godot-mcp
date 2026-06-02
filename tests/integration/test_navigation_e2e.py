"""End-to-end navigation test against a live editor (issue #43)."""

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
SCRATCH = "res://tmp_e2e_navigation.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_navigation.tscn"


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

        region = await _ok(
            bridge,
            "cmd_setup_navigation_region",
            {"parent_path": ".", "region_type": "NavigationRegion3D", "name": "Nav"},
        )
        assert region["node_path"] == "Nav" and region["created"] is True
        agent = await _ok(
            bridge,
            "cmd_setup_navigation_agent",
            {
                "parent_path": ".",
                "agent_type": "NavigationAgent3D",
                "name": "Agent",
                "properties": {"radius": 1.5, "path_desired_distance": 0.5},
            },
        )
        assert agent["agent_type"] == "NavigationAgent3D"

        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        by_name = {c["name"]: c["type"] for c in tree["tree"]["children"]}
        assert by_name["Nav"] == "NavigationRegion3D"
        assert by_name["Agent"] == "NavigationAgent3D"

        # bake the (empty) navmesh — completes synchronously without error
        baked = await _ok(bridge, "cmd_bake_navigation_mesh", {"node_path": "Nav"})
        assert baked["baked"] is True

        # navigation layers from 1-based bit indices
        layers = await _ok(
            bridge, "cmd_set_navigation_layers", {"node_path": "Nav", "layers": [1, 3]}
        )
        assert layers["navigation_layers"] == 5  # bits 1 and 3 → 1 | 4

        # validation: bad region/agent type, non-region bake, no navigation_layers, bad bits
        bad_region = await bridge.send(
            "cmd_setup_navigation_region", {"parent_path": ".", "region_type": "Node3D"}
        )
        assert bad_region.ok is False and bad_region.error == "VALIDATION_ERROR"
        bad_agent = await bridge.send(
            "cmd_setup_navigation_agent", {"parent_path": ".", "agent_type": "Node3D"}
        )
        assert bad_agent.ok is False and bad_agent.error == "VALIDATION_ERROR"
        await _create(bridge, "Plain", "Node3D")
        not_region = await bridge.send("cmd_bake_navigation_mesh", {"node_path": "Plain"})
        assert not_region.ok is False and not_region.error == "VALIDATION_ERROR"
        no_layers = await bridge.send(
            "cmd_set_navigation_layers", {"node_path": "Plain", "layers": [1]}
        )
        assert no_layers.ok is False and no_layers.error == "VALIDATION_ERROR"
        bad_bits = await bridge.send(
            "cmd_set_navigation_layers", {"node_path": "Nav", "layers": "nope"}
        )
        assert bad_bits.ok is False and bad_bits.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_navigation() -> None:
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
