"""End-to-end theme/UI test against a live editor (issue #46)."""

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
SCRATCH = "res://tmp_e2e_theme.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_theme.tscn"
THEME_PATH = "res://tmp_e2e_theme_res.tres"
THEME_FILE = GODOT_PROJECT / "tmp_e2e_theme_res.tres"


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
        await _ok(bridge, "cmd_create_scene", {"root_type": "Control", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _create(bridge, "Panel", "Panel")

        # create + save a theme on the Control
        theme = await _ok(
            bridge, "cmd_create_theme", {"node_path": "Panel", "save_path": THEME_PATH}
        )
        assert theme["created"] is True and theme["theme_path"] == THEME_PATH
        assert THEME_FILE.exists(), "theme should be saved to disk"

        # overrides on the Control
        color = await _ok(
            bridge,
            "cmd_set_theme_color",
            {"node_path": "Panel", "name": "font_color", "color": "#ff8800"},
        )
        assert color["name"] == "font_color"
        size = await _ok(
            bridge,
            "cmd_set_theme_font_size",
            {"node_path": "Panel", "name": "font_size", "size": 24},
        )
        assert size["size"] == 24
        box = await _ok(
            bridge,
            "cmd_set_theme_stylebox",
            {
                "node_path": "Panel",
                "name": "panel",
                "stylebox_type": "StyleBoxFlat",
                "properties": {"bg_color": "#222233", "corner_radius_top_left": 8},
            },
        )
        assert box["stylebox_type"] == "StyleBoxFlat"

        # validation: non-Control target, bad stylebox type, non-positive size, bad save path
        await _create(bridge, "Plain", "Node2D")
        not_control = await bridge.send("cmd_create_theme", {"node_path": "Plain"})
        assert not_control.ok is False and not_control.error == "VALIDATION_ERROR"
        not_control_color = await bridge.send(
            "cmd_set_theme_color", {"node_path": "Plain", "name": "font_color", "color": "#fff"}
        )
        assert not_control_color.ok is False and not_control_color.error == "VALIDATION_ERROR"
        bad_box = await bridge.send(
            "cmd_set_theme_stylebox",
            {"node_path": "Panel", "name": "panel", "stylebox_type": "Node"},
        )
        assert bad_box.ok is False and bad_box.error == "VALIDATION_ERROR"
        bad_size = await bridge.send(
            "cmd_set_theme_font_size", {"node_path": "Panel", "name": "font_size", "size": 0}
        )
        assert bad_size.ok is False and bad_size.error == "VALIDATION_ERROR"
        bad_path = await bridge.send(
            "cmd_create_theme", {"node_path": "Panel", "save_path": "/tmp/x.tres"}
        )
        assert bad_path.ok is False and bad_path.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_theme_ui() -> None:
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
        THEME_FILE.unlink(missing_ok=True)
