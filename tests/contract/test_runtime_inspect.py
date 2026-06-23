"""Contract tests for runtime inspection tools (issue #35)."""

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
        case "cmd_monitor_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "monitoring": True,
                    "node_path": p["node_path"],
                    "property": p["property"],
                    "samples": p["samples"],
                },
            )
        case "cmd_get_property_samples":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "connected": True,
                    "node_path": "/root/Main",
                    "property": "position",
                    "samples": [{"frame": 1, "value": {"x": 0, "y": 0}}],
                    "error": "",
                },
            )
        case "cmd_find_ui_elements":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "elements": [
                        {
                            "path": "/root/Main/Button",
                            "name": "Button",
                            "node_class": "Button",
                            "visible": True,
                            "rect": {"x": 10, "y": 20, "w": 100, "h": 40},
                            "text": "Play",
                        }
                    ],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_read_only_in_runtime_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_runtime_find_ui_elements" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_runtime_monitor_property",
        "godot_runtime_get_property_samples",
        "godot_runtime_find_ui_elements",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "read_only" for n in expected)


async def test_monitor_and_collect_samples() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        mon = await client.call_tool(
            "godot_runtime_monitor_property",
            {"node_path": "/root/Main", "property": "position", "samples": 5},
        )
        samples = await client.call_tool("godot_runtime_get_property_samples", {})
    assert mon.structured_content["monitoring"] is True
    assert mon.structured_content["samples"] == 5
    sc = samples.structured_content
    assert sc["ready"] is True and sc["property"] == "position"
    assert sc["samples"][0]["value"] == {"x": 0, "y": 0}


async def test_find_ui_elements() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_find_ui_elements", {"class_filter": "Button", "visible_only": True}
        )
    sc = result.structured_content
    assert sc["ready"] is True
    el = sc["elements"][0]
    assert el["node_class"] == "Button"
    assert el["text"] == "Play"
    assert el["rect"]["w"] == 100
