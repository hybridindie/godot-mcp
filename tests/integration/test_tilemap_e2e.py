"""End-to-end tilemap test against a live editor (issues #45, #82).

Exercises the cell-erase / get / fill / clear / layers paths and validation, then the
TileSet authoring chain from #82 (create_tileset → add_tileset_atlas_source →
create_tile) — which finally lets tilemap_set_cell place a *real*, non-empty tile. A
PlaceholderTexture2D stands in for an imported image so the atlas grid resolves without
a real asset import.
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
TEX = "res://tmp_e2e_tile_tex.tres"
TILESET = "res://tmp_e2e_tileset.tres"
TILESET_FILE = GODOT_PROJECT / "tmp_e2e_tileset.tres"
# .tres resources + their Godot 4.4 .uid sidecars, all cleaned up after the run.
_ARTIFACTS = [
    "tmp_e2e_tilemap.tscn",
    "tmp_e2e_tile_tex.tres",
    "tmp_e2e_tile_tex.tres.uid",
    "tmp_e2e_tileset.tres",
    "tmp_e2e_tileset.tres.uid",
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

        # --- TileSet authoring (issue #82): build a TileSet and place a REAL tile ---
        # PlaceholderTexture2D is a Texture2D whose size we set directly, so the atlas
        # grid (64 / 16 = 4x4) resolves without importing an actual image file.
        await _ok(
            bridge,
            "cmd_create_resource",
            {
                "type": "PlaceholderTexture2D",
                "resource_path": TEX,
                "properties": {"size": {"x": 64, "y": 64}},
            },
        )
        # node-backed: TileSet on the TileMapLayer → atlas source → tile
        ts = await _ok(bridge, "cmd_create_tileset", {"node_path": "Ground", "tile_size": [16, 16]})
        assert ts["created"] is True and ts["tile_size"] == [16, 16]
        src = await _ok(
            bridge,
            "cmd_add_tileset_atlas_source",
            {"node_path": "Ground", "texture_path": TEX, "region_size": [16, 16]},
        )
        sid = src["source_id"]
        await _ok(
            bridge,
            "cmd_create_tile",
            {"node_path": "Ground", "source_id": sid, "atlas_coords": [0, 0]},
        )
        # the payoff: set_cell now places a real, non-empty tile that reads back
        await _ok(
            bridge,
            "cmd_tilemap_set_cell",
            {"node_path": "Ground", "coords": [2, 2], "source_id": sid, "atlas_coords": [0, 0]},
        )
        placed = await _ok(
            bridge, "cmd_tilemap_get_cell", {"node_path": "Ground", "coords": [2, 2]}
        )
        assert placed["empty"] is False and placed["source_id"] == sid

        # file-backed: author a TileSet saved as .tres, then add a source + tile to it
        saved = await _ok(bridge, "cmd_create_tileset", {"save_path": TILESET, "tile_size": [8, 8]})
        assert saved["tileset_path"] == TILESET and TILESET_FILE.exists()
        fsrc = await _ok(
            bridge,
            "cmd_add_tileset_atlas_source",
            {"tileset_path": TILESET, "texture_path": TEX, "region_size": [8, 8]},
        )
        await _ok(
            bridge,
            "cmd_create_tile",
            {"tileset_path": TILESET, "source_id": fsrc["source_id"], "atlas_coords": [1, 1]},
        )

        # validation: a node without a tile_set, and an out-of-atlas tile
        no_ts = await bridge.send(
            "cmd_add_tileset_atlas_source",
            {"node_path": "Grid", "texture_path": TEX, "region_size": [16, 16]},
        )
        assert no_ts.ok is False and no_ts.error == "VALIDATION_ERROR"
        oob = await bridge.send(
            "cmd_create_tile",
            {"node_path": "Ground", "source_id": sid, "atlas_coords": [99, 99]},
        )
        assert oob.ok is False and oob.error == "VALIDATION_ERROR"
        # targeting both a node and a .tres is ambiguous — rejected addon-side too
        both = await bridge.send(
            "cmd_add_tileset_atlas_source",
            {
                "node_path": "Ground",
                "tileset_path": TILESET,
                "texture_path": TEX,
                "region_size": [16, 16],
            },
        )
        assert both.ok is False and both.error == "VALIDATION_ERROR"
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
        for artifact in _ARTIFACTS:
            (GODOT_PROJECT / artifact).unlink(missing_ok=True)
