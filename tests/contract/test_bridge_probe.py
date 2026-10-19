"""Contract tests for the replaced-editor bridge probe (issue #702).

A replaced editor must be able to ask "is the bridge free?" without displacing
the editor that currently owns it. The probe path answers busy while a peer is
connected; when free, it adopts the SAME connection so there is no reconnect
race.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


async def test_busy_probe_does_not_displace_the_active_editor() -> None:
    active = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(active))
    await bridge.connect()

    probe = FakeAddonConnection(path="/probe")
    await bridge._handle_peer(probe)

    assert probe.closed, "a busy probe is closed"
    assert bridge._conn is active, "the active editor must stay attached"
    assert json.loads(probe.sent[-1]) == {"ok": True, "busy": True}
    await bridge.close()


async def test_free_probe_is_promoted_without_a_second_connection() -> None:
    bridge = Bridge(BridgeConfig())
    probe = FakeAddonConnection(path="/probe")

    task = asyncio.create_task(bridge._handle_peer(probe))
    for _ in range(50):
        if probe.sent:
            break
        await asyncio.sleep(0)

    assert json.loads(probe.sent[0]) == {"ok": True, "busy": False}
    assert bridge._conn is probe, "the probe connection itself becomes the peer"

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await bridge.close()
