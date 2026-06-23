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
        case "cmd_record_input":
            return ResponseEnvelope.success(cmd.id, {"recording": True})
        case "cmd_stop_recording":
            return ResponseEnvelope.success(cmd.id, {"recording": False})
        case "cmd_get_recording":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "connected": True,
                    "events": [{"type": "key", "key": "Space", "pressed": True}],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_in_input_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_input_simulate_key" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        tools = {t.name: t for t in await client.list_tools()}
    runtime = {
        "godot_input_simulate_key",
        "godot_input_simulate_mouse",
        "godot_input_simulate_action",
        "godot_input_play_sequence",
    }
    assert runtime <= set(tools)
    assert all(tools[n].meta["safety_class"] == "runtime" for n in runtime)
    assert tools["godot_input_get_stats"].meta["safety_class"] == "read_only"


async def test_simulate_key_mouse_action() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        key = await client.call_tool("godot_input_simulate_key", {"key": "Space", "pressed": True})
        mouse = await client.call_tool(
            "godot_input_simulate_mouse", {"x": 10, "y": 20, "button": "left"}
        )
        action = await client.call_tool("godot_input_simulate_action", {"action": "ui_accept"})
    assert key.structured_content["kind"] == "key" and key.structured_content["sent"] is True
    assert mouse.structured_content["kind"] == "mouse"
    assert action.structured_content["kind"] == "action"


async def test_play_input_sequence_counts_events() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        seq = await client.call_tool(
            "godot_input_play_sequence",
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
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        stats = await client.call_tool("godot_input_get_stats", {})
    assert stats.structured_content["connected"] is True
    assert stats.structured_content["injected"] == 3


async def test_record_and_stop_returns_replayable_events() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        rec = await client.call_tool("godot_input_record", {})
        stopped = await client.call_tool("godot_input_stop_recording", {})
    assert rec.structured_content["recording"] is True
    events = stopped.structured_content["events"]
    assert events and events[0]["type"] == "key" and events[0]["key"] == "Space"


async def test_record_input_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_input_record"].meta["safety_class"] == "runtime"
    assert tools["godot_input_stop_recording"].meta["safety_class"] == "read_only"
