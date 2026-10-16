"""Contract tests for Tier 2 debugger stack / eval tools (issue #110 / #677).

``evaluate_expression`` runs in the running game via the runtime probe (#677) and
requires a play session with the probe. ``get_stack_frames`` and
``get_frame_variables`` are **unsupported** on Godot 4.7 (the paused-frame
debugger protocol is not exposed to editor debugger plugins) and return a
structured ``UNSUPPORTED`` error.
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
        case "cmd_evaluate_expression":
            p = cmd.params
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "expression": p.get("expression"),
                    "value": 42,
                    "evaluated": True,
                    "error": "",
                },
            )
        case "cmd_get_stack_frames" | "cmd_get_frame_variables":
            # #677: unsupported on Godot 4.7 — structured error, not silent empty.
            return ResponseEnvelope.failure(
                cmd.id, "UNSUPPORTED", "not exposed to editor debugger plugins"
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
    async with Client(server, mode="legacy") as client:
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


async def test_get_stack_frames_is_unsupported() -> None:
    # #677: the paused-frame stack is not plugin-accessible on Godot 4.7.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_get_stack_frames", {}, raise_on_error=False
        )
    assert result.is_error and "UNSUPPORTED" in str(result.content)
    assert "cmd_get_stack_frames" in _commands(conn)


async def test_evaluate_expression_runs_in_game() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_evaluate_expression", {"expression": "1 + 1"}
        )
    sc = result.structured_content
    assert sc["expression"] == "1 + 1"
    assert sc["value"] == 42
    assert sc["evaluated"] is True
    assert "cmd_evaluate_expression" in _commands(conn)


async def test_get_frame_variables_is_unsupported() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_get_frame_variables", {}, raise_on_error=False
        )
    assert result.is_error and "UNSUPPORTED" in str(result.content)
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
