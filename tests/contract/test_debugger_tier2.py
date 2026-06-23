"""Contract tests for Tier 2 debugger step/continue tools (issue #110 follow-up).

Four new `runtime` tools in the existing `debugger` toolset:
step_into, step_over, step_out, continue_execution.

All require an active play session with a valid debug session, and the game
must be paused (either at a breakpoint or after force_break).
"""

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
        case (
            "cmd_set_breakpoint"
            | "cmd_remove_breakpoint"
            | "cmd_clear_breakpoints"
            | "cmd_force_break"
        ):
            return ResponseEnvelope.success(cmd.id, {})
        case "cmd_step_into" | "cmd_step_over" | "cmd_step_out":
            return ResponseEnvelope.success(cmd.id, {"stepped": True})
        case "cmd_continue_execution":
            return ResponseEnvelope.success(cmd.id, {"running": True})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_debugger_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_debugger_step_into" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "godot_debugger_set_breakpoint",
        "godot_debugger_remove_breakpoint",
        "godot_debugger_clear_breakpoints",
        "godot_debugger_force_break",
        "godot_debugger_step_into",
        "godot_debugger_step_over",
        "godot_debugger_step_out",
        "godot_debugger_continue_execution",
    } <= names


async def test_step_into() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_step_into", {})
    assert result.structured_content["stepped"] is True
    assert "cmd_step_into" in _commands(conn)


async def test_step_over() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_step_over", {})
    assert result.structured_content["stepped"] is True
    assert "cmd_step_over" in _commands(conn)


async def test_step_out() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_step_out", {})
    assert result.structured_content["stepped"] is True
    assert "cmd_step_out" in _commands(conn)


async def test_continue_execution() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_continue_execution", {})
    assert result.structured_content["running"] is True
    assert "cmd_continue_execution" in _commands(conn)


async def test_tier2_tools_are_runtime_class() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        for name in (
            "godot_debugger_step_into",
            "godot_debugger_step_over",
            "godot_debugger_step_out",
            "godot_debugger_continue_execution",
        ):
            tool = next(t for t in await client.list_tools() if t.name == name)
            assert tool.meta is not None
            assert tool.meta.get("safety_class") == "runtime"
