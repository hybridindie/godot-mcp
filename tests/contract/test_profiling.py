"""Contract tests for profiling tools (issue #38)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_MONITORS = {"fps": 60.0, "memory_static": 1048576.0, "object_count": 42.0, "draw_calls": 0.0}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_get_editor_performance":
            return ResponseEnvelope.success(cmd.id, {"monitors": _MONITORS})
        case "cmd_get_performance_monitors":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "connected": True, "ready": True, "monitors": _MONITORS}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_read_only_in_profiling_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_profiling_get_editor_performance" not in {
            t.name for t in await client.list_tools()
        }
        await client.call_tool("godot_enable_toolset", {"category": "profiling"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_profiling_get_editor_performance",
        "godot_profiling_get_performance_monitors",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "read_only" for n in expected)


async def test_editor_performance_returns_monitors() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "profiling"})
        result = await client.call_tool("godot_profiling_get_editor_performance", {})
    monitors = result.structured_content["monitors"]
    assert monitors["fps"] == 60.0
    assert monitors["object_count"] == 42.0


async def test_game_performance_monitors() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "profiling"})
        result = await client.call_tool("godot_profiling_get_performance_monitors", {})
    sc = result.structured_content
    assert sc["playing"] is True and sc["connected"] is True and sc["ready"] is True
    assert sc["monitors"]["memory_static"] == 1048576.0


async def test_game_performance_not_connected_returns_hint() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_performance_monitors":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "playing": True,
                    "connected": False,
                    "ready": True,
                    "monitors": {},
                    "hint": "add the probe",
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "profiling"})
        result = await client.call_tool("godot_profiling_get_performance_monitors", {})
    assert result.structured_content["connected"] is False
    assert "probe" in result.structured_content["hint"]
