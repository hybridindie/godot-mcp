"""Contract tests for Tier 2 debugger stack / eval tools (issue #110 follow-up).

Three new ``runtime`` tools in the existing ``debugger`` toolset:
get_stack_frames, evaluate_expression, get_frame_variables.

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
        case "cmd_get_stack_frames":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "frames": [
                        {"file": "res://main.gd", "line": 7, "func": "_ready"},
                        {"file": "res://player.gd", "line": 42, "func": "take_damage"},
                    ]
                },
            )
        case "cmd_evaluate_expression":
            p = cmd.params
            return ResponseEnvelope.success(
                cmd.id,
                {"expression": p.get("expression"), "value": 42},
            )
        case "cmd_get_frame_variables":
            p = cmd.params
            frame = p.get("frame", 0)
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "frame": frame,
                    "locals": [{"name": "health", "value": 100.0}],
                    "members": [{"name": "speed", "value": 300}],
                    "globals": [{"name": "GlobalState", "value": "<Dictionary>"}],
                },
            )
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
        assert "godot_debugger_get_stack_frames" not in {t.name for t in await client.list_tools()}
        assert "godot_debugger_evaluate_expression" not in {
            t.name for t in await client.list_tools()
        }
        assert "godot_debugger_get_frame_variables" not in {
            t.name for t in await client.list_tools()
        }
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
        "godot_debugger_get_stack_frames",
        "godot_debugger_evaluate_expression",
        "godot_debugger_get_frame_variables",
    } <= names


async def test_get_stack_frames() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_get_stack_frames", {})
    frames = result.structured_content["frames"]
    assert len(frames) == 2
    assert frames[0]["file"] == "res://main.gd"
    assert frames[0]["line"] == 7
    assert frames[0]["func"] == "_ready"
    assert "cmd_get_stack_frames" in _commands(conn)


async def test_evaluate_expression() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_evaluate_expression", {"expression": "player.health * 2", "frame": 0}
        )
    sc = result.structured_content
    assert sc["expression"] == "player.health * 2"
    assert sc["value"] == 42
    assert "cmd_evaluate_expression" in _commands(conn)


async def test_get_frame_variables() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool("godot_debugger_get_frame_variables", {"frame": 1})
    sc = result.structured_content
    assert sc["frame"] == 1
    assert sc["locals"][0]["name"] == "health"
    assert sc["members"][0]["name"] == "speed"
    assert sc["globals"][0]["name"] == "GlobalState"
    assert "cmd_get_frame_variables" in _commands(conn)


async def test_stack_eval_tools_are_runtime_class() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        for name in (
            "godot_debugger_get_stack_frames",
            "godot_debugger_evaluate_expression",
            "godot_debugger_get_frame_variables",
        ):
            tool = next(t for t in await client.list_tools() if t.name == name)
            assert tool.meta is not None
            assert tool.meta.get("safety_class") == "runtime"
