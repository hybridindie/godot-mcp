"""Contract tests for debugger breakpoint control tools (issue #110, Tier 1)."""

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
    match cmd.command:
        case "cmd_set_breakpoint":
            p = cmd.params
            return ResponseEnvelope.success(
                cmd.id,
                {"breakpoint_set": True, "path": p.get("path"), "line": p.get("line")},
            )
        case "cmd_remove_breakpoint":
            p = cmd.params
            return ResponseEnvelope.success(
                cmd.id,
                {"breakpoint_removed": True, "path": p.get("path"), "line": p.get("line")},
            )
        case "cmd_clear_breakpoints":
            return ResponseEnvelope.success(cmd.id, {"breakpoints_cleared": True})
        case "cmd_force_break":
            return ResponseEnvelope.success(cmd.id, {"force_break_sent": True})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_in_debugger_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_debugger_set_breakpoint" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_debugger_set_breakpoint",
        "godot_debugger_remove_breakpoint",
        "godot_debugger_clear_breakpoints",
        "godot_debugger_force_break",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "runtime" for n in expected)


async def test_set_breakpoint() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_set_breakpoint", {"path": "res://player.gd", "line": 42}
        )
    sc = result.structured_content
    assert sc["breakpoint_set"] is True
    assert sc["path"] == "res://player.gd"
    assert sc["line"] == 42


async def test_remove_breakpoint() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_remove_breakpoint", {"path": "res://player.gd", "line": 42}
        )
    sc = result.structured_content
    assert sc["breakpoint_removed"] is True
    assert sc["path"] == "res://player.gd"
    assert sc["line"] == 42


async def test_clear_breakpoints() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_clear_breakpoints", {})
    assert result.structured_content["breakpoints_cleared"] is True


async def test_force_break() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_force_break", {})
    assert result.structured_content["force_break_sent"] is True
