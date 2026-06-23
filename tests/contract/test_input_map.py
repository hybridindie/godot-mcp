"""Contract tests for input map editing tools (issue #81).

Drive the real FastMCP server with a fake addon peer: verify safety classes,
dry_run, routing, and structured preconditions.
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
    p = cmd.params
    match cmd.command:
        case "cmd_add_input_action":
            return ResponseEnvelope.success(
                cmd.id, {"name": p["name"], "added": True, "deadzone": p.get("deadzone", 0.5)}
            )
        case "cmd_remove_input_action":
            return ResponseEnvelope.success(cmd.id, {"name": p["name"], "removed": True})
        case "cmd_add_input_event":
            return ResponseEnvelope.success(
                cmd.id, {"action": p["action"], "event_index": 0, "added": True}
            )
        case "cmd_clear_input_action_events":
            return ResponseEnvelope.success(cmd.id, {"action": p["action"], "cleared": True})
        case "cmd_get_input_action_events":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "action": p["action"],
                    "deadzone": 0.5,
                    "events": [
                        {
                            "event_type": "key",
                            "keycode": "Space",
                            "shift": False,
                            "ctrl": True,
                            "alt": False,
                            "meta": False,
                        },
                        {"event_type": "mouse", "button": "left"},
                    ],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_input_map_tool_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_input_map_add_action"].meta["safety_class"] == "mutating"
    assert tools["godot_input_map_remove_action"].meta["safety_class"] == "destructive"
    assert tools["godot_input_map_add_event"].meta["safety_class"] == "mutating"
    assert tools["godot_input_map_clear_action_events"].meta["safety_class"] == "destructive"


async def test_add_input_action_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_add_action", {"name": "jump", "deadzone": 0.2}
        )
    assert result.structured_content["added"] is True
    assert result.structured_content["deadzone"] == 0.2
    assert "cmd_add_input_action" in _commands(conn)


async def test_add_input_action_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_add_action", {"name": "jump", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["added"] is False
    assert "cmd_add_input_action" not in _commands(conn)


async def test_remove_input_action_without_confirm_is_blocked() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_remove_action", {"name": "jump"}, raise_on_error=False
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_remove_input_action" not in _commands(conn)


async def test_remove_input_action_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_remove_action", {"name": "jump", "confirm": True}
        )
    assert result.structured_content["removed"] is True
    assert "cmd_remove_input_action" in _commands(conn)


async def test_add_input_event_routes_to_addon() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_add_event",
            {"action": "jump", "event_type": "key", "keycode": "Space"},
        )
    assert result.structured_content["added"] is True
    assert result.structured_content["event_index"] == 0
    assert "cmd_add_input_event" in _commands(conn)


async def test_add_input_event_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_add_event",
            {"action": "jump", "event_type": "key", "keycode": "Space", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["added"] is False
    assert "cmd_add_input_event" not in _commands(conn)


async def test_clear_input_action_events_without_confirm_is_blocked() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_clear_action_events", {"action": "jump"}, raise_on_error=False
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_clear_input_action_events" not in _commands(conn)


async def test_clear_input_action_events_with_confirm_proceeds() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(
            "godot_input_map_clear_action_events", {"action": "jump", "confirm": True}
        )
    assert result.structured_content["cleared"] is True
    assert "cmd_clear_input_action_events" in _commands(conn)


async def test_get_input_action_events_returns_detail() -> None:
    # #219 P2: read each event's full detail so remove/clear are invertible.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool("godot_input_map_get_action_events", {"action": "jump"})
        tools = {t.name: t for t in await client.list_tools()}
    data = result.structured_content
    assert data["action"] == "jump"
    assert data["deadzone"] == 0.5
    key = data["events"][0]
    assert key["event_type"] == "key" and key["keycode"] == "Space" and key["ctrl"] is True
    assert data["events"][1] == {"event_type": "mouse", "button": "left"}
    assert tools["godot_input_map_get_action_events"].meta["safety_class"] == "read_only"
    assert "cmd_get_input_action_events" in _commands(conn)
