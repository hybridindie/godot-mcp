"""Contract tests for push-on-change property sampling (issue #536).

Pin the new ``on_change_only``/``epsilon`` params on ``monitor_property`` through
the envelope: the server forwards them to the addon verbatim, defaults preserve
the dedup-on behavior, and the typed result echoes them.
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
    if cmd.command == "cmd_monitor_property":
        return ResponseEnvelope.success(
            cmd.id,
            {
                "monitoring": True,
                "node_path": cmd.params["node_path"],
                "property": cmd.params["property"],
                "samples": cmd.params["samples"],
                "on_change_only": cmd.params["on_change_only"],
                "epsilon": cmd.params["epsilon"],
            },
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_monitor_forwards_on_change_params() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool(
            "godot_runtime_monitor_property",
            {
                "node_path": "/root/Main",
                "property": "position",
                "samples": 5,
                "on_change_only": False,
                "epsilon": 0.5,
            },
        )
    params = conn.last_command().params
    assert params["on_change_only"] is False
    assert params["epsilon"] == 0.5


async def test_monitor_defaults_on_change_only_true() -> None:
    # Default is push-on-change (the new behavior); old sampling is opt-out.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool(
            "godot_runtime_monitor_property", {"node_path": "/root/Main", "property": "position"}
        )
    params = conn.last_command().params
    assert params["on_change_only"] is True
    assert params["epsilon"] == 0.0001


async def test_result_echoes_on_change_params() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_monitor_property",
            {"node_path": "/root/Main", "property": "position", "on_change_only": False},
        )
    sc = result.structured_content
    assert sc["on_change_only"] is False
    assert sc["epsilon"] == 0.0001