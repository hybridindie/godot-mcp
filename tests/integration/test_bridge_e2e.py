"""End-to-end bridge test: live Python server ↔ live Godot editor (issue #3, #276).

The Python ``Bridge`` starts its **listener** and the headless Godot *editor* (the
addon, now a WebSocket *client*) connects *out* to it over a real socket; we then
assert a live ``ping`` → ``pong``. This is the automated form of the acceptance
criteria "addon and server can establish a connection" and "a ping command returns a
valid pong response". Skipped when no Godot binary is present.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, serve_and_await_editor

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# A non-default port so the test's listener never collides with a real editor session
# (the addon picks it up via GODOT_MCP_BRIDGE_URL).
BRIDGE_URL = "ws://127.0.0.1:9097"


async def _ping_live_bridge() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    # Server listens; the editor (addon client) connects out to it. It takes a few
    # seconds to boot and the addon reconnects with backoff, so wait generously.
    connected = await serve_and_await_editor(bridge)
    assert connected, "the addon never connected to the bridge (editor not running?)"
    try:
        assert await bridge.ping() is True, "live ping did not return pong"
    finally:
        await bridge.close()


def test_live_editor_answers_ping() -> None:
    assert GODOT_BIN is not None  # for type-checkers; pytestmark guards at runtime
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_ping_live_bridge())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
