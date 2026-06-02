"""Contract tests for theme/UI tools (issue #46)."""

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
        case "cmd_get_node_properties":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Panel"})
        case "cmd_create_theme":
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": p["node_path"], "theme_path": p["save_path"], "created": True},
            )
        case "cmd_set_theme_color":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "name": p["name"]}
            )
        case "cmd_set_theme_font_size":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "name": p["name"], "size": p["size"]}
            )
        case "cmd_set_theme_stylebox":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "name": p["name"],
                    "stylebox_type": p["stylebox_type"],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_theme_ui_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "create_theme" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "theme_ui"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {"create_theme", "set_theme_color", "set_theme_font_size", "set_theme_stylebox"}
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_create_theme_and_overrides() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "theme_ui"})
        theme = await client.call_tool(
            "create_theme", {"node_path": "UI", "save_path": "res://ui.tres"}
        )
        color = await client.call_tool(
            "set_theme_color", {"node_path": "UI", "name": "font_color", "color": "#ff8800"}
        )
        size = await client.call_tool(
            "set_theme_font_size", {"node_path": "UI", "name": "font_size", "size": 24}
        )
        box = await client.call_tool(
            "set_theme_stylebox",
            {
                "node_path": "UI",
                "name": "panel",
                "stylebox_type": "StyleBoxFlat",
                "properties": {"bg_color": "#222222"},
            },
        )
    assert theme.structured_content["theme_path"] == "res://ui.tres"
    assert theme.structured_content["created"] is True
    assert color.structured_content["name"] == "font_color"
    assert size.structured_content["size"] == 24
    assert box.structured_content["stylebox_type"] == "StyleBoxFlat"


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "theme_ui"})
        result = await client.call_tool(
            "set_theme_color",
            {"node_path": "UI", "name": "font_color", "color": "#ffffff", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_set_theme_color" not in _commands(conn)
