"""Contract tests for audio tools (issue #44)."""

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
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node"})
        case "cmd_add_audio_player":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "player_type": p["player_type"],
                    "created": True,
                },
            )
        case "cmd_get_audio_bus_layout":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "buses": [
                        {
                            "index": 0,
                            "name": "Master",
                            "volume_db": 0.0,
                            "effects": [{"index": 0, "type": "AudioEffectReverb", "enabled": True}],
                        }
                    ]
                },
            )
        case "cmd_add_audio_bus":
            return ResponseEnvelope.success(cmd.id, {"index": 1, "name": p["name"]})
        case "cmd_add_audio_bus_effect":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "bus": p["bus"],
                    "bus_index": 1,
                    "effect_type": p["effect_type"],
                    "effect_index": 0,
                },
            )
        case "cmd_remove_audio_bus":
            return ResponseEnvelope.success(cmd.id, {"name": "SFX", "index": 1, "removed": True})
        case "cmd_remove_audio_bus_effect":
            return ResponseEnvelope.success(
                cmd.id, {"bus": "SFX", "bus_index": 1, "effect_index": 0, "removed": True}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_audio_toolset_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_audio_add_bus" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        tools = {t.name: t for t in await client.list_tools()}
    mutating = {"godot_audio_add_player", "godot_audio_add_bus", "godot_audio_add_bus_effect"}
    assert mutating <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in mutating)
    # the layout read is exposed in the same toolset but is read_only
    assert tools["godot_audio_get_bus_layout"].meta["safety_class"] == "read_only"


async def test_player_bus_and_effect() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        player = await client.call_tool(
            "godot_audio_add_player",
            {
                "parent_path": ".",
                "player_type": "AudioStreamPlayer2D",
                "properties": {"volume_db": -6.0},
            },
        )
        bus = await client.call_tool("godot_audio_add_bus", {"name": "Music", "volume_db": -3.0})
        effect = await client.call_tool(
            "godot_audio_add_bus_effect", {"bus": "Music", "effect_type": "AudioEffectReverb"}
        )
    assert player.structured_content["player_type"] == "AudioStreamPlayer2D"
    assert player.structured_content["node_path"] == "./AudioStreamPlayer2D"
    assert bus.structured_content["name"] == "Music" and bus.structured_content["index"] == 1
    assert effect.structured_content["effect_type"] == "AudioEffectReverb"
    assert effect.structured_content["effect_index"] == 0


async def test_get_bus_layout_reports_buses_and_effects() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        layout = await client.call_tool("godot_audio_get_bus_layout", {})
    buses = layout.structured_content["buses"]
    assert buses[0]["name"] == "Master"
    assert buses[0]["effects"][0]["type"] == "AudioEffectReverb"


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        result = await client.call_tool("godot_audio_add_bus", {"name": "SFX", "dry_run": True})
    assert result.structured_content["dry_run"] is True
    assert "cmd_add_audio_bus" not in _commands(conn)


async def test_audio_bus_removers_are_destructive() -> None:
    # #219 G8: the removers are destructive (confirm-gated), the inverse of the adders.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_audio_remove_bus"].meta["safety_class"] == "destructive"
    assert tools["godot_audio_remove_bus_effect"].meta["safety_class"] == "destructive"


async def test_remove_audio_bus_requires_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        blocked = await client.call_tool(
            "godot_audio_remove_bus", {"bus": "SFX"}, raise_on_error=False
        )
        assert blocked.is_error and "confirm" in str(blocked.content)
        assert "cmd_remove_audio_bus" not in _commands(conn)
        ok = await client.call_tool("godot_audio_remove_bus", {"bus": "SFX", "confirm": True})
    assert ok.structured_content["removed"] is True
    assert ok.structured_content["index"] == 1
    assert "cmd_remove_audio_bus" in _commands(conn)


async def test_remove_audio_bus_dry_run_sends_no_command() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        result = await client.call_tool("godot_audio_remove_bus", {"bus": "SFX", "dry_run": True})
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["removed"] is False
    assert "cmd_remove_audio_bus" not in _commands(conn)


async def test_remove_audio_bus_effect_requires_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        blocked = await client.call_tool(
            "godot_audio_remove_bus_effect", {"bus": "SFX", "effect_index": 0}, raise_on_error=False
        )
        assert blocked.is_error and "confirm" in str(blocked.content)
        assert "cmd_remove_audio_bus_effect" not in _commands(conn)
        ok = await client.call_tool(
            "godot_audio_remove_bus_effect", {"bus": "SFX", "effect_index": 0, "confirm": True}
        )
    assert ok.structured_content["removed"] is True
    assert ok.structured_content["effect_index"] == 0
    assert "cmd_remove_audio_bus_effect" in _commands(conn)
