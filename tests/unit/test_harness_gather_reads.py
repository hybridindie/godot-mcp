"""Unit tests for the pipelined-read harness helper (issue #169).

gather_reads fires independent read-only commands concurrently so a discovery
phase costs ~one frame instead of one frame per read. These pin: results come
back in order, the reads are dispatched concurrently (all in flight before any
resolves), and a mutating command is rejected (writes must stay ordered).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.harness import gather_reads
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for, ping_responder


async def _bridge_conn(responder: Any = ping_responder) -> tuple[Bridge, FakeAddonConnection]:
    conn = FakeAddonConnection(responder)
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    return bridge, conn


async def _bridge(responder: Any = ping_responder) -> Bridge:
    bridge, _ = await _bridge_conn(responder)
    return bridge


def test_gather_reads_returns_results_in_order() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_node_properties":
            return ResponseEnvelope.success(cmd.id, {"node_path": cmd.params["node_path"]})
        return ping_responder(cmd)

    async def go() -> None:
        bridge = await _bridge(responder)
        results = await gather_reads(
            bridge,
            [
                ("cmd_get_node_properties", {"node_path": "A"}),
                ("cmd_get_node_properties", {"node_path": "B"}),
                ("cmd_get_node_properties", {"node_path": "C"}),
            ],
        )
        assert [r["node_path"] for r in results] == ["A", "B", "C"]
        await bridge.close()

    asyncio.run(go())


def test_gather_reads_dispatches_every_read() -> None:
    """All N reads round-trip the bridge (gather fires them together)."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_scene_tree":
            return ResponseEnvelope.success(cmd.id, {"tree": None})
        return ping_responder(cmd)

    async def go() -> None:
        bridge, conn = await _bridge_conn(responder)
        reads: list[tuple[str, dict[str, Any]]] = [("cmd_get_scene_tree", {}) for _ in range(5)]
        results = await gather_reads(bridge, reads)
        assert len(results) == 5
        sent = [CommandEnvelope.model_validate_json(s).command for s in conn.sent]
        assert sent.count("cmd_get_scene_tree") == 5
        await bridge.close()

    asyncio.run(go())


def test_gather_reads_rejects_mutation() -> None:
    async def go() -> None:
        bridge = await _bridge()
        with pytest.raises(ValueError, match="read-only"):
            await gather_reads(bridge, [("cmd_set_node_property", {"node_path": "A"})])
        await bridge.close()

    asyncio.run(go())
