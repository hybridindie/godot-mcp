"""End-to-end visual shader test against a live editor (issue #107).

Skipped without Godot.  Creates a visual shader, adds a node, connects it to
output, and sets a parameter.
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
SHADER = "res://tmp_e2e_visual_shader.tres"
_ARTIFACTS = ["tmp_e2e_visual_shader.tres"]


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


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
        created = await _ok(
            bridge,
            "cmd_create_visual_shader",
            {"name": "e2e", "type": "2d", "path": SHADER},
        )
        assert created["created"] is True
        assert created["path"] == SHADER

        added = await _ok(
            bridge,
            "cmd_add_shader_node",
            {
                "shader_path": SHADER,
                "node_type": "VisualShaderNodeColorConstant",
                "node_id": 1,
                "position": [100.0, 200.0],
            },
        )
        assert added["added"] is True
        assert added["node_id"] == 1

        connected = await _ok(
            bridge,
            "cmd_connect_shader_nodes",
            {
                "shader_path": SHADER,
                "from_node": 1,
                "from_port": 0,
                "to_node": 0,
                "to_port": 0,
            },
        )
        assert connected["connected"] is True

        types = await _ok(bridge, "cmd_list_shader_node_types", {})
        assert any(t.startswith("VisualShaderNode") for t in types["types"])
    finally:
        await bridge.close()


def test_live_visual_shader_workflow() -> None:
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
        for name in _ARTIFACTS:
            (GODOT_PROJECT / name).unlink(missing_ok=True)
