"""End-to-end input-map test against a live editor (issue #651).

Covers the input-map commands that had no live coverage: add action -> add key
event -> read it back -> clear -> add again -> remove. Edits ProjectSettings
(project.godot), so it does not need a play session or a display — it runs in CI
even headless. Skipped without a Godot binary.
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
    serve_and_await_editor,
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = e2e_bridge_url()
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
ACTION = "mcp_e2e_input_action"


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
        added = await _ok(bridge, "cmd_add_input_action", {"name": ACTION, "deadzone": 0.3})
        assert added["added"] is True and added["deadzone"] == 0.3

        ev = await _ok(
            bridge,
            "cmd_add_input_event",
            {"action": ACTION, "event_type": "key", "keycode": "Space"},
        )
        assert ev["added"] is True and ev["event_index"] == 0

        read = await _ok(bridge, "cmd_get_input_action_events", {"action": ACTION})
        assert read["deadzone"] == 0.3
        events = read.get("events", [])
        assert len(events) == 1, events
        assert events[0].get("event_type") == "key", events[0]

        cleared = await _ok(
            bridge, "cmd_clear_input_action_events", {"action": ACTION, "confirm": True}
        )
        assert cleared["cleared"] is True
        after_clear = await _ok(bridge, "cmd_get_input_action_events", {"action": ACTION})
        assert after_clear.get("events", []) == []

        removed = await _ok(bridge, "cmd_remove_input_action", {"name": ACTION, "confirm": True})
        assert removed["removed"] is True
        missing = await bridge.send("cmd_get_input_action_events", {"action": ACTION})
        assert missing.ok is False and missing.error == "RESOURCE_NOT_FOUND"

        # remove without confirm is refused (destructive gate)
        await _ok(bridge, "cmd_add_input_action", {"name": ACTION})
        guarded = await bridge.send("cmd_remove_input_action", {"name": ACTION})
        assert guarded.ok is False and guarded.required == "confirm"
    finally:
        # Best-effort cleanup so a failure mid-run doesn't leave the action behind.
        try:
            await bridge.send("cmd_remove_input_action", {"name": ACTION, "confirm": True})
        except Exception:
            pass
        await bridge.close()


def test_live_input_map() -> None:
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
        PROJECT_GODOT.write_bytes(snapshot)  # restore (drop the test action)
