"""Contract tests for input simulation tools (issue #36)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_simulate_key":
            return ResponseEnvelope.success(cmd.id, {"sent": True, "kind": "key", "count": 1})
        case "cmd_simulate_mouse":
            return ResponseEnvelope.success(cmd.id, {"sent": True, "kind": "mouse", "count": 1})
        case "cmd_simulate_action":
            return ResponseEnvelope.success(cmd.id, {"sent": True, "kind": "action", "count": 1})
        case "cmd_play_input_sequence":
            return ResponseEnvelope.success(
                cmd.id, {"sent": True, "kind": "sequence", "count": len(p["events"])}
            )
        case "cmd_get_input_stats":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "connected": True, "injected": 3}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_in_input_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "simulate_key" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "input"})
        tools = {t.name: t for t in await client.list_tools()}
    runtime = {"simulate_key", "simulate_mouse", "simulate_action", "play_input_sequence"}
    assert runtime <= set(tools)
    assert all(tools[n].meta["safety_class"] == "runtime" for n in runtime)
    assert tools["get_input_stats"].meta["safety_class"] == "read_only"


async def test_simulate_key_mouse_action() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "input"})
        key = await client.call_tool("simulate_key", {"key": "Space", "pressed": True})
        mouse = await client.call_tool("simulate_mouse", {"x": 10, "y": 20, "button": "left"})
        action = await client.call_tool("simulate_action", {"action": "ui_accept"})
    assert key.structured_content["kind"] == "key" and key.structured_content["sent"] is True
    assert mouse.structured_content["kind"] == "mouse"
    assert action.structured_content["kind"] == "action"


async def test_play_input_sequence_counts_events() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "input"})
        seq = await client.call_tool(
            "play_input_sequence",
            {
                "events": [
                    {"type": "key", "key": "A"},
                    {"type": "action", "action": "ui_accept"},
                    {"type": "mouse", "x": 5, "y": 5, "button": "left"},
                ],
                "delay_ms": 50,
            },
        )
    assert seq.structured_content["kind"] == "sequence"
    assert seq.structured_content["count"] == 3


async def test_get_input_stats() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "input"})
        stats = await client.call_tool("get_input_stats", {})
    assert stats.structured_content["connected"] is True
    assert stats.structured_content["injected"] == 3
