"""End-to-end profiling test against a live editor (issue #38)."""

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
SCRATCH = "res://tmp_e2e_profiling.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_profiling.tscn"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
PROBE = "res://addons/godot_mcp/mcp_runtime_probe.gd"


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
        # editor monitors are available without a play session
        editor = await _ok(bridge, "cmd_get_editor_performance", {})
        m = editor["monitors"]
        assert "fps" in m and "memory_static" in m and "object_count" in m
        assert m["object_count"] > 0  # the editor has live objects

        # game monitors require a play session with the probe
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # not playing yet -> game monitors are a structured precondition error
        no_session = await bridge.send("cmd_get_performance_monitors", {})
        assert no_session.ok is False and no_session.error == "PRECONDITION_FAILED"

        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        game: dict[str, Any] = {}
        for _ in range(30):
            game = await _ok(bridge, "cmd_get_performance_monitors", {})
            if game.get("connected") and game.get("ready") and game.get("monitors"):
                break
            await asyncio.sleep(0.5)
        assert game["connected"] is True
        gm = game["monitors"]
        assert "fps" in gm and "object_count" in gm
        assert gm["object_count"] > 0  # the running game has live objects

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_profiling() -> None:
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
        SCRATCH_FILE.unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)
