"""End-to-end bridge test: live Python server ↔ live Godot editor (issue #3).

Launches the headless Godot *editor* (which enables the plugin and starts the
WebSocket server), connects the real Python ``Bridge`` over a real socket, and
asserts a live ``ping`` → ``pong``. This is the automated form of the acceptance
criteria "addon and server can establish a connection" and "a ping command
returns a valid pong response". Skipped when no Godot binary is present.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"


async def _ping_live_bridge() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    # The editor takes a few seconds to boot and start listening; retry generously.
    connected = False
    for _ in range(60):
        try:
            await bridge.connect()
            connected = True
            break
        except Exception:
            await asyncio.sleep(0.5)
    assert connected, "could not connect to the addon bridge (editor not listening?)"
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
    )
    try:
        asyncio.run(_ping_live_bridge())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
