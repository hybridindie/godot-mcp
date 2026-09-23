"""End-to-end auto-refresh test against a live editor (issue #561).

With GODOT_MCP_AUTO_REFRESH=1 in the editor's environment, a file written by
the TEST process (outside the editor) shows up in the editor's filesystem view
within one timer period — without the editor ever having focus.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    needs_display,
    serve_and_await_editor,
)

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    needs_display,
]

BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_autorefresh.txt"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_autorefresh.txt"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_seen(bridge: Bridge, path: str, budget_s: float) -> bool:
    """Poll the filesystem tree for the file; the auto-refresh timer should
    pick it up within one period (env-set to ~3s) without editor focus."""
    for _ in range(int(budget_s / 0.5)):
        tree = await _ok(bridge, "cmd_get_filesystem_tree", {"directory": "res://", "max_depth": 1})
        names = [c["name"] for c in tree["tree"].get("children", [])]
        if os.path.basename(path) in names:
            return True
        await asyncio.sleep(0.5)
    return False


def test_live_auto_refresh_picks_up_external_write() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={
            **os.environ,
            "GODOT_MCP_BRIDGE_URL": BRIDGE_URL,
            "GODOT_MCP_AUTO_REFRESH": "1",
            "GODOT_MCP_AUTO_REFRESH_INTERVAL": "3",
        },
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


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    try:
        # The file does not exist yet; the editor's fs view must not have it.
        tree = await _ok(bridge, "cmd_get_filesystem_tree", {"directory": "res://", "max_depth": 1})
        names = [c["name"] for c in tree["tree"].get("children", [])]
        assert "tmp_e2e_autorefresh.txt" not in names

        # An OUT-OF-BAND write: the test process creates the file directly.
        # The editor stays unfocused the whole time — only the addon's
        # auto-refresh timer can pick this up.
        SCRATCH_FILE.write_text("external edit\n")

        # One timer period (3s) + slack: the file must appear in the editor's
        # view with no focus and no MCP-side write.
        assert await _wait_seen(bridge, str(SCRATCH_FILE), 10.0), (
            "the auto-refresh timer did not pick up the external write within its period"
        )
    finally:
        await bridge.close()