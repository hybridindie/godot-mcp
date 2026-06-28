"""Bridge lazy-reconnect on send.

Regression for the most common "MCP not connecting in Godot" failure: the server
process starts *before* the Godot editor/addon is listening, so the one-shot startup
``connect()`` fails — and without lazy reconnect every later ``send()`` returns
``BRIDGE_DISCONNECTED`` forever, even once the addon is up. A send must transparently
(re)connect instead of staying dead.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import ErrorCode
from tests.fakes import FakeAddonConnection, flaky_connector

pytestmark = pytest.mark.asyncio


async def _yield_sleep(_seconds: float) -> None:
    """A backoff sleep that yields to the loop without real delay (deterministic)."""
    await asyncio.sleep(0)


async def test_send_reconnects_after_failed_startup_connect() -> None:
    # Startup connect fails (Godot not up yet); the addon comes up before the first
    # send. That send must reconnect and succeed — not return BRIDGE_DISCONNECTED.
    bridge = Bridge(
        BridgeConfig(),
        connector=flaky_connector(fail_times=1, connection=FakeAddonConnection()),
    )
    with pytest.raises(ConnectionError):
        await bridge.connect()  # the one-shot startup attempt, while Godot is down
    assert bridge.connected is False

    resp = await bridge.send("cmd_ping")
    assert resp.ok, f"send should have reconnected, got {resp.error}"
    assert resp.result == {"pong": True}
    assert bridge.connected is True
    await bridge.close()


async def test_send_still_fails_cleanly_when_addon_stays_down() -> None:
    # When the addon really is unreachable, send still returns a structured
    # BRIDGE_DISCONNECTED (never raises) — the reconnect attempt just fails.
    bridge = Bridge(
        BridgeConfig(),
        connector=flaky_connector(fail_times=99, connection=FakeAddonConnection()),
    )
    with pytest.raises(ConnectionError):
        await bridge.connect()

    resp = await bridge.send("cmd_ping")
    assert not resp.ok
    assert resp.error == ErrorCode.BRIDGE_DISCONNECTED
    assert bridge.connected is False


async def test_stay_connected_supervisor_connects_once_addon_comes_up() -> None:
    # The server boots before Godot: the supervisor must connect on its own once the
    # addon is listening, so `connected` flips to True for preconditions/health/dock
    # with no tool call. flaky_connector fails twice (Godot still down), then connects.
    bridge = Bridge(
        BridgeConfig(),
        connector=flaky_connector(fail_times=2, connection=FakeAddonConnection()),
        sleep=_yield_sleep,
        rand=lambda: 0.0,
    )
    assert bridge.connected is False
    supervisor = asyncio.create_task(bridge.stay_connected())
    try:
        for _ in range(100):  # let the supervisor tick; it connects within a few
            if bridge.connected:
                break
            await asyncio.sleep(0)
        assert bridge.connected is True
    finally:
        supervisor.cancel()
        with suppress(asyncio.CancelledError):
            await supervisor
        await bridge.close()
