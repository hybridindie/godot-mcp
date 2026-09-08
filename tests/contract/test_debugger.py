"""Contract tests for debugger breakpoint control tools (issue #110, Tier 1)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from mcp_server.tools import debugger as debugger_module
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
            return ResponseEnvelope.success(
                cmd.id, {"force_break_sent": True, "breaked": True}
            )
        case "cmd_get_debug_break_state":  # #411: server polls for the break state
            return ResponseEnvelope.success(cmd.id, {"breaked": True})
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
    # #411: the result must report whether the game actually reached a break
    # state — force_break_sent alone was a silent no-op trap.
    assert result.structured_content["breaked"] is True


async def test_force_break_poll_timeout_reports_breaked_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honest-failure path: the flag is sent but the game never reports a break
    state before the poll deadline — the result must say ``breaked=false`` so an
    agent knows the break did NOT land (#411: force_break_sent alone was the
    silent no-op trap; a regression hardcoding breaked=true must fail here).
    Poll constants are patched short so the loop runs without real waiting."""
    monkeypatch.setattr(debugger_module, "_BREAK_POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(debugger_module, "_BREAK_POLL_TIMEOUT_S", 0.0)
    polled = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_force_break":
            return ResponseEnvelope.success(cmd.id, {"force_break_sent": True})
        if cmd.command == "cmd_get_debug_break_state":
            polled["n"] += 1
            return ResponseEnvelope.success(cmd.id, {"breaked": False})
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_force_break", {})
    assert result.structured_content["force_break_sent"] is True
    assert result.structured_content["breaked"] is False
    assert polled["n"] >= 1  # the poll actually ran (not short-circuited)
