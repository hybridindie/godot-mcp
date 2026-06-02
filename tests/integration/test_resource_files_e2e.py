"""End-to-end resource-file + autoload test against a live editor (issue #34).

Creates/reads/edits a real .tres and registers/unregisters an autoload. The autoload
write touches project.godot, so the test snapshots and restores it to avoid
polluting the tracked file. Skipped without Godot.
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
TRES = "res://tmp_e2e_shape.tres"
AUTO_GD = "res://tmp_e2e_auto.gd"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
_ARTIFACTS = ["tmp_e2e_shape.tres", "tmp_e2e_auto.gd", "tmp_e2e_auto.gd.uid"]


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
        # create → read
        await _ok(
            bridge,
            "cmd_create_resource",
            {
                "type": "RectangleShape2D",
                "resource_path": TRES,
                "properties": {"size": {"x": 4, "y": 5}},
            },
        )
        read = await _ok(bridge, "cmd_read_resource", {"resource_path": TRES})
        assert read["type"] == "RectangleShape2D"
        assert read["properties"]["size"] == {"x": 4.0, "y": 5.0}

        # edit → read
        await _ok(
            bridge,
            "cmd_set_resource_property",
            {"resource_path": TRES, "property": "size", "value": {"x": 10, "y": 20}},
        )
        after = await _ok(bridge, "cmd_read_resource", {"resource_path": TRES})
        assert after["properties"]["size"] == {"x": 10.0, "y": 20.0}

        # autoload register → visible in project info → unregister
        await _ok(bridge, "cmd_write_script", {"script_path": AUTO_GD, "content": "extends Node\n"})
        await _ok(bridge, "cmd_register_autoload", {"name": "E2EAuto", "path": AUTO_GD})
        info = await _ok(bridge, "cmd_get_project_info", {})
        assert "E2EAuto" in info["autoloads"]
        unreg = await _ok(bridge, "cmd_unregister_autoload", {"name": "E2EAuto"})
        assert unreg["unregistered"] is True

        # Validation: setting a property on a non-.tres path is a structured error.
        bad = await bridge.send(
            "cmd_set_resource_property",
            {"resource_path": AUTO_GD, "property": "x", "value": 1},
        )
        assert bad.ok is False and bad.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_resource_workflow() -> None:
    assert GODOT_BIN is not None
    project_godot_snapshot = PROJECT_GODOT.read_text()
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
        # Restore project.godot exactly (the autoload register/save rewrote it).
        PROJECT_GODOT.write_text(project_godot_snapshot)
        for name in _ARTIFACTS:
            (GODOT_PROJECT / name).unlink(missing_ok=True)
