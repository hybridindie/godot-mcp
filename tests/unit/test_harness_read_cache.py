"""Unit tests for the client-side read cache harness helper (issue #170).

ReadCache memoizes read-only results per session and drops them on a mutation, so
a harness stops re-fetching stable scene state. These pin: a repeat read is served
from cache (no second round-trip), distinct params cache separately, invalidate and
write force a re-fetch, and a mutation cannot be read through the cache.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.harness import ReadCache
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for, ping_responder


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_get_scene_tree":
        return ResponseEnvelope.success(cmd.id, {"tree": {"name": "Main"}})
    if cmd.command == "cmd_get_node_properties":
        return ResponseEnvelope.success(cmd.id, {"node_path": cmd.params["node_path"]})
    if cmd.command == "cmd_set_node_property":
        return ResponseEnvelope.success(cmd.id, {"updated": True})
    return ping_responder(cmd)


async def _bridge_conn() -> tuple[Bridge, FakeAddonConnection]:
    conn = FakeAddonConnection(_responder)
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    return bridge, conn


def _count(conn: FakeAddonConnection, command: str) -> int:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent].count(command)


def test_repeat_read_served_from_cache() -> None:
    async def go() -> None:
        bridge, conn = await _bridge_conn()
        cache = ReadCache(bridge)
        a = await cache.read("cmd_get_scene_tree")
        b = await cache.read("cmd_get_scene_tree")
        assert a == b == {"tree": {"name": "Main"}}
        assert _count(conn, "cmd_get_scene_tree") == 1  # second read hit the cache
        await bridge.close()

    asyncio.run(go())


def test_distinct_params_cache_separately() -> None:
    async def go() -> None:
        bridge, conn = await _bridge_conn()
        cache = ReadCache(bridge)
        await cache.read("cmd_get_node_properties", {"node_path": "A"})
        await cache.read("cmd_get_node_properties", {"node_path": "B"})
        await cache.read("cmd_get_node_properties", {"node_path": "A"})  # cached
        assert _count(conn, "cmd_get_node_properties") == 2
        await bridge.close()

    asyncio.run(go())


def test_invalidate_forces_refetch() -> None:
    async def go() -> None:
        bridge, conn = await _bridge_conn()
        cache = ReadCache(bridge)
        await cache.read("cmd_get_scene_tree")
        cache.invalidate()
        await cache.read("cmd_get_scene_tree")
        assert _count(conn, "cmd_get_scene_tree") == 2
        await bridge.close()

    asyncio.run(go())


def test_write_invalidates_cache() -> None:
    async def go() -> None:
        bridge, conn = await _bridge_conn()
        cache = ReadCache(bridge)
        await cache.read("cmd_get_scene_tree")
        # A mutation through write() drops cached reads so the next read is fresh.
        await cache.write("cmd_set_node_property", {"node_path": "A", "property": "x", "value": 1})
        await cache.read("cmd_get_scene_tree")
        assert _count(conn, "cmd_get_scene_tree") == 2
        assert _count(conn, "cmd_set_node_property") == 1
        await bridge.close()

    asyncio.run(go())


def test_read_rejects_mutation() -> None:
    async def go() -> None:
        bridge, _ = await _bridge_conn()
        cache = ReadCache(bridge)
        with pytest.raises(ValueError, match="read-only"):
            await cache.read("cmd_set_node_property", {"node_path": "A"})
        await bridge.close()

    asyncio.run(go())
