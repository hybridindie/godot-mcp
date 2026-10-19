"""End-to-end project scaffold rollback test (issue #700).

The scaffold is all-or-nothing: a failure after the directories/script/autoload
were applied must restore project settings, remove created files/directories, and
leave any pre-existing obstruction untouched.
"""

from __future__ import annotations

import asyncio
import os
import shutil
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
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = e2e_bridge_url()
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
SCENES = GODOT_PROJECT / "scenes"
OBSTRUCTION = "res://scenes/main.tscn/keep.gd"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        before = await _ok(bridge, "cmd_get_setting", {"name": "application/config/name"})

        # Make the main-scene save fail after every earlier step has run: a
        # directory at res://scenes/main.tscn is not a writable scene path.
        await _ok(
            bridge,
            "cmd_write_script",
            {"script_path": OBSTRUCTION, "content": "extends Node\n"},
        )

        response = await bridge.send(
            "cmd_scaffold_project",
            {
                "type": "2d_platformer",
                "project_name": "RollbackTest",
                "main_scene": "main",
                "confirm": True,
            },
        )
        assert response.ok is False
        assert response.error == "INTERNAL_ERROR"
        assert "rolled back" in (response.hint or "").lower(), response.hint

        # Settings restored.
        after = await _ok(bridge, "cmd_get_setting", {"name": "application/config/name"})
        assert after["value"] == before["value"]

        # Autoload removed.
        info = await _ok(bridge, "cmd_get_project_info", {})
        assert "GameState" not in info["autoloads"]

        # Created files/directories removed; the pre-existing obstruction stays.
        assert not (GODOT_PROJECT / "scripts" / "game_state.gd").exists()
        assert not (GODOT_PROJECT / "scripts").exists()
        assert not (GODOT_PROJECT / "assets").exists()
        assert not (GODOT_PROJECT / "shaders").exists()
        assert (SCENES / "main.tscn" / "keep.gd").exists()
    finally:
        await bridge.close()


def test_live_scaffold_failure_rolls_back_everything() -> None:
    assert GODOT_BIN is not None
    project_snapshot = PROJECT_GODOT.read_text()
    scenes_existed = SCENES.exists()
    scripts_existed = (GODOT_PROJECT / "scripts").exists()
    assets_existed = (GODOT_PROJECT / "assets").exists()
    shaders_existed = (GODOT_PROJECT / "shaders").exists()

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

        PROJECT_GODOT.write_text(project_snapshot)
        for path, existed in (
            (SCENES, scenes_existed),
            (GODOT_PROJECT / "scripts", scripts_existed),
            (GODOT_PROJECT / "assets", assets_existed),
            (GODOT_PROJECT / "shaders", shaders_existed),
        ):
            if not existed and path.exists():
                shutil.rmtree(path, ignore_errors=True)
