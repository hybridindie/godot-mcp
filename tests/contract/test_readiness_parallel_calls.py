"""Contract: a parallel read does not refuse a mutation with EDITOR_BUSY (#762 follow-up).

``Bridge.editor_status`` is ``busy`` whenever any command is pending, so a
client that issues tool calls in parallel gets EDITOR_BUSY on the mutation.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio

# Commands the fake addon never answers: they stay in flight for the test.
_WITHHELD = {"cmd_bake_navigation_mesh", "cmd_get_scene_tree"}


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command in _WITHHELD:
        return None
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": True, "path": "res://m.tscn"})
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_create_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": f"{command.params['parent_path']}/{command.params['name']}",
                "created": True,
            },
        )
    return make_addon_responder(godot_version="4.7.2-stable")(command)


async def _heartbeat(conn: FakeAddonConnection, bridge: Bridge, clock: list[float]) -> None:
    await conn.push({"command": "cmd_editor_status", "params": {"status": "ready"}})
    for _ in range(100):
        if bridge._last_heartbeat == clock[0]:  # noqa: SLF001 — wait for the bridge to ingest it
            return
        await asyncio.sleep(0.01)
    raise AssertionError("heartbeat never reached the bridge")


async def test_parallel_read_does_not_refuse_a_mutation_with_editor_busy() -> None:
    clock = [1_000.0]
    conn = FakeAddonConnection(_responder)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn), clock=lambda: clock[0])
    server = create_server(config, bridge=bridge)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await _heartbeat(conn, bridge, clock)
        read = asyncio.create_task(bridge.send("cmd_get_scene_tree", {}))
        await asyncio.sleep(0.01)
        try:
            result = await client.call_tool(
                "godot_scene_edit_create_node",
                {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
                raise_on_error=False,
            )
        finally:
            read.cancel()
    assert not result.is_error, result.structured_content
    assert "cmd_create_node" in [json.loads(s).get("command") for s in conn.sent]


def _withhold_create(command: Any) -> ResponseEnvelope | None:
    if command.command == "cmd_create_node":
        return None
    return _responder(command)


async def test_second_mutation_while_one_is_pending_is_refused() -> None:
    clock = [1_000.0]
    conn = FakeAddonConnection(_withhold_create)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn), clock=lambda: clock[0])
    server = create_server(config, bridge=bridge)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        if "cmd_create_node" not in bridge._mutating_commands:  # noqa: SLF001
            bridge.set_mutating_commands(frozenset({"cmd_create_node"}))
        await _heartbeat(conn, bridge, clock)
        first = asyncio.create_task(
            bridge.send("cmd_create_node", {"parent_path": ".", "name": "A"})
        )
        await asyncio.sleep(0.01)
        try:
            result = await client.call_tool(
                "godot_scene_edit_create_node",
                {"parent_path": ".", "node_type": "Node2D", "node_name": "B"},
                raise_on_error=False,
            )
        finally:
            first.cancel()
    assert result.is_error
    assert result.structured_content is not None
    assert result.structured_content["error"] == "EDITOR_BUSY"
    sent = [json.loads(s).get("command") for s in conn.sent]
    assert sent.count("cmd_create_node") == 1
