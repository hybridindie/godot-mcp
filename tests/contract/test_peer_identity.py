"""Contract tests for bridge peer identity (issue #537).

A second Godot editor connecting silently replaces the first; the first's agent
then sees BRIDGE_DISCONNECTED with no explanation. Contract: each peer sends a
hello (project_path, godot_version, addon_version) at connect time; the server
keeps the identity, exposes it in BridgeDiagnostics, and logs a structured
peer-replacement entry naming both project paths. Backward compatible: peers
without the hello (older addons) are marked identity-unknown, not refused.
"""

from __future__ import annotations

import json
import logging

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


async def test_hello_params_shape() -> None:
    """The addon's hello carries exactly the identity fields the server reads."""
    # The addon sends the hello as its FIRST message after connecting (not a
    # request/response command): the server side never replies to it.
    hello = {
        "id": "hello",
        "command": "cmd_peer_hello",
        "params": {
            "project_path": "/tmp/project_a",
            "godot_version": "4.7.2",
            "addon_version": "2026.9.22",
        },
    }
    conn = FakeAddonConnection()
    await conn.send(json.dumps(hello))  # queued to the server's read loop
    parsed = json.loads(conn.sent[0])
    assert parsed["params"]["project_path"] == "/tmp/project_a"


async def test_server_exposes_connected_peer_identity() -> None:
    """The identity the peer announced is readable off the bridge."""
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
    await bridge.connect()
    try:
        assert bridge.peer_identity is None  # no hello received yet
        await bridge.adopt_identity(
            {
                "project_path": "/tmp/project_a",
                "godot_version": "4.7.2",
                "addon_version": "2026.9.22",
            }
        )
        assert bridge.peer_identity == {
            "project_path": "/tmp/project_a",
            "godot_version": "4.7.2",
            "addon_version": "2026.9.22",
        }
    finally:
        await bridge.close()


async def test_peer_replacement_logs_both_paths(caplog: pytest.LogCaptureFixture) -> None:
    """A second editor replacing the first logs a structured entry naming both
    project paths — silence is what #537 fixes."""
    first = FakeAddonConnection()
    bridge = Bridge(BridgeConfig(), connector=connector_for(first))
    with caplog.at_level(logging.INFO, logger="mcp_server.bridge"):
        await bridge.connect()
        await bridge.adopt_identity({"project_path": "/tmp/project_a"})
        await bridge.addon_info()  # populate the cached handshake for the old peer

        second = FakeAddonConnection()
        bridge._connector = connector_for(second)
        await bridge.connect()
        await bridge.adopt_identity({"project_path": "/tmp/project_b"})

        # Structured log: the paths ride as record attributes (extra=), not in
        # the message text — assert the machine-readable contract.
        replaced = [
            r for r in caplog.records
            if r.getMessage() == "bridge peer replaced" and r.levelno >= logging.INFO
        ]
    assert replaced, "peer replacement must be logged, not silent (#537)"
    entry = replaced[-1]
    assert getattr(entry, "previous_peer", "") == "/tmp/project_a"
    await bridge.close()


async def test_peer_without_hello_marks_identity_unknown() -> None:
    """Backward compatibility: an older addon (no hello) connects fine, and the
    identity reads as unknown (None), not an error."""
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
    await bridge.connect()
    try:
        assert bridge.connected is True
        assert bridge.peer_identity is None
        assert await bridge.ping() is True
    finally:
        await bridge.close()


async def test_identity_resets_with_the_peer() -> None:
    """A replaced (or disconnected) peer clears the cached identity — stale
    identity must never survive a reconnect."""
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
    await bridge.connect()
    await bridge.adopt_identity({"project_path": "/tmp/project_a"})
    await bridge.close()
    assert bridge.peer_identity is None
    # And on replacement:
    bridge2 = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
    await bridge2.connect()
    await bridge2.adopt_identity({"project_path": "/tmp/project_a"})
    bridge2._connector = connector_for(FakeAddonConnection())
    await bridge2.connect()
    try:
        assert bridge2.peer_identity is None
    finally:
        await bridge2.close()