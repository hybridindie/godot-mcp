"""End-to-end bridge auth test against a live editor (issue #538).

With GODOT_MCP_BRIDGE_TOKEN set on both sides, the addon authenticates as its
first message and the bridge serves it; a wrong token on the addon side is
refused at the handshake (structured refusal, reconnect loop). The no-token
path is covered by test_bridge_e2e (byte-identical, unchanged).
"""

from __future__ import annotations

import asyncio
import os
import subprocess

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
TOKEN = "e2e-bridge-token"


async def _wait_auth_outcome(bridge: Bridge, want_connected: bool) -> bool:
    """Poll the connection state for a bounded budget (deterministic — the addon
    connects and authenticates within a couple of frames; a refused peer loops)."""
    for _ in range(40):
        if not want_connected:
            # A refused peer never flips `connected`; two attempts prove the
            # handshake refusal ran and the addon's reconnect loop kicked in.
            if bridge.peer_attempts >= 2:
                return bridge.connected is False
        elif bridge.connected:
            return True
        await asyncio.sleep(0.25)
    return bridge.connected == want_connected


def _launch_editor(token: str) -> subprocess.Popen[bytes]:
    assert GODOT_BIN is not None  # pytestmark guards at runtime; this narrows types
    env = {**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL, "GODOT_MCP_BRIDGE_TOKEN": token}
    return subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


def _terminate(editor: subprocess.Popen[bytes]) -> None:
    editor.terminate()
    try:
        editor.wait(timeout=10)
    except subprocess.TimeoutExpired:
        editor.kill()


async def _matching_tokens_connect() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL, auth_token=TOKEN))
    connected = await serve_and_await_editor(bridge)
    assert connected, "the addon never connected"
    try:
        assert await _wait_auth_outcome(bridge, want_connected=True), (
            "a matching token must authenticate and serve"
        )
        assert await bridge.ping() is True, "authenticated bridge must answer ping"
    finally:
        await bridge.close()


def test_live_editor_authenticates_with_matching_token() -> None:
    assert GODOT_BIN is not None
    editor = _launch_editor(TOKEN)
    try:
        asyncio.run(_matching_tokens_connect())
    finally:
        _terminate(editor)


async def _wrong_token_is_refused() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL, auth_token=TOKEN))
    await bridge.serve()
    # The addon connects out, sends its wrong token, is refused, and reconnects
    # with backoff — peer_attempts climbs without `connected` ever flipping.
    try:
        assert await _wait_auth_outcome(bridge, want_connected=False), (
            "a wrong token must be refused at the handshake"
        )
        assert bridge.peer_attempts >= 2, "the refused addon must retry (reconnect loop)"
        response = await bridge.send("cmd_ping")
        assert response.ok is False
        assert response.error == "BRIDGE_DISCONNECTED"
    finally:
        await bridge.close()


def test_live_editor_with_wrong_token_is_refused() -> None:
    assert GODOT_BIN is not None
    editor = _launch_editor("wrong-token")
    try:
        asyncio.run(_wrong_token_is_refused())
    finally:
        _terminate(editor)