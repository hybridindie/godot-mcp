"""End-to-end tilemap test against a live editor (issue #45).

Tile *placement* needs a configured TileSet (atlas source + texture), which can't be
built through the current tool surface — so the live test exercises the cell-erase /
get / fill / clear / layers paths and validation, while the full place-a-tile data
round-trip is covered by the contract test.
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
SCRATCH = "res://tmp_e2e_tilemap.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_tilemap.tscn"


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
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _create(bridge, "Ground", "TileMapLayer")
        await _create(bridge, "Grid", "TileMap")

        # TileMapLayer reports its single layer
        layers = await _ok(bridge, "cmd_tilemap_layers", {"node_path": "Ground"})
        assert layers["node_type"] == "TileMapLayer"
        assert layers["layers"] == [{"index": 0, "name": "Ground", "enabled": True}]

        # an empty cell reads back empty
        cell = await _ok(bridge, "cmd_tilemap_get_cell", {"node_path": "Ground", "coords": [0, 0]})
        assert cell["empty"] is True and cell["source_id"] == -1

        # erase set_cell + erase fill are valid without a TileSet and are undoable
        erased = await _ok(
            bridge,
            "cmd_tilemap_set_cell",
            {"node_path": "Ground", "coords": [2, 2], "source_id": -1},
        )
        assert erased["coords"] == [2, 2]
        filled = await _ok(
            bridge,
            "cmd_tilemap_fill_rect",
            {"node_path": "Ground", "rect": [0, 0, 2, 2], "source_id": -1},
        )
        assert filled["cells"] == 4

        # clear an empty layer reports zero cells; TileMapLayer reports layer null
        cleared = await _ok(bridge, "cmd_tilemap_clear", {"node_path": "Ground"})
        assert cleared["cleared"] == 0 and cleared["layer"] is None

        # TileMap lists its layers (count not hard-asserted across versions)
        grid_layers = await _ok(bridge, "cmd_tilemap_layers", {"node_path": "Grid"})
        assert grid_layers["node_type"] == "TileMap" and isinstance(grid_layers["layers"], list)

        # validation: non-tilemap node, out-of-range TileMap layer, oversized fill
        await _create(bridge, "Plain", "Node2D")
        not_tilemap = await bridge.send(
            "cmd_tilemap_get_cell", {"node_path": "Plain", "coords": [0, 0]}
        )
        assert not_tilemap.ok is False and not_tilemap.error == "VALIDATION_ERROR"
        bad_layer = await bridge.send(
            "cmd_tilemap_set_cell",
            {"node_path": "Grid", "coords": [0, 0], "source_id": -1, "layer": 99},
        )
        assert bad_layer.ok is False and bad_layer.error == "VALIDATION_ERROR"
        too_big = await bridge.send(
            "cmd_tilemap_fill_rect",
            {"node_path": "Ground", "rect": [0, 0, 200, 200], "source_id": -1},
        )
        assert too_big.ok is False and too_big.error == "VALIDATION_ERROR"
        # malformed coords are rejected, not silently treated as (0, 0)
        bad_coords = await bridge.send(
            "cmd_tilemap_set_cell", {"node_path": "Ground", "coords": [5], "source_id": -1}
        )
        assert bad_coords.ok is False and bad_coords.error == "VALIDATION_ERROR"
        bad_get = await bridge.send("cmd_tilemap_get_cell", {"node_path": "Ground", "coords": []})
        assert bad_get.ok is False and bad_get.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_tilemap() -> None:
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
