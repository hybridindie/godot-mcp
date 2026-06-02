"""End-to-end project & filesystem test against a live editor (issue #32).

Runs the fs-tree / search / settings / UID handlers against the real project. The
set_setting test writes project.godot, so the test snapshots and restores it.
Skipped without Godot.
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
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
ADDON = "res://addons/godot_mcp"


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
        # filesystem tree of the addon dir includes its scripts
        tree = await _ok(bridge, "cmd_get_filesystem_tree", {"directory": ADDON, "max_depth": 1})
        names = [c["name"] for c in tree["tree"]["children"]]
        assert "command_router.gd" in names

        # search by glob, and by content
        by_glob = await _ok(bridge, "cmd_search_files", {"directory": ADDON, "name_glob": "*.gd"})
        assert any(m.endswith("command_router.gd") for m in by_glob["matches"])
        by_content = await _ok(
            bridge,
            "cmd_search_files",
            {"directory": ADDON, "content": "class_name MCPCommandRouter"},
        )
        assert any(m.endswith("command_router.gd") for m in by_content["matches"])

        # settings: existing + missing
        present = await _ok(bridge, "cmd_get_setting", {"name": "application/config/name"})
        assert present["exists"] is True and present["value"] == "godot-mcp"
        missing = await _ok(bridge, "cmd_get_setting", {"name": "nonexistent/key"})
        assert missing["exists"] is False

        # write a setting, read it back
        await _ok(
            bridge,
            "cmd_set_setting",
            {"name": "application/config/description", "value": "e2e test description"},
        )
        readback = await _ok(bridge, "cmd_get_setting", {"name": "application/config/description"})
        assert readback["value"] == "e2e test description"

        # UID round-trip on a script that has a .uid
        to_uid = await _ok(
            bridge, "cmd_path_to_uid", {"path": "res://addons/godot_mcp/godot_mcp.gd"}
        )
        assert to_uid["uid"].startswith("uid://")
        back = await _ok(bridge, "cmd_uid_to_path", {"uid": to_uid["uid"]})
        assert back["path"] == "res://addons/godot_mcp/godot_mcp.gd"

        # Sandbox: paths outside the project (res://) are rejected.
        outside = await bridge.send("cmd_get_filesystem_tree", {"directory": "/etc"})
        assert outside.ok is False and outside.error == "VALIDATION_ERROR"
    finally:
        await bridge.close()


def test_live_project_fs() -> None:
    assert GODOT_BIN is not None
    snapshot = PROJECT_GODOT.read_text()
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
        PROJECT_GODOT.write_text(snapshot)  # undo the set_setting write
