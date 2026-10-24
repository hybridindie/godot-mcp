"""Contract tests for project-registered tools (#761).

In-memory client + fake addon peer. The addon's scanner is exercised end to end
in ``tests/integration/test_project_tools_e2e.py`` (requires a Godot binary);
these tests pin the server half: registration, gating, safety and the wire shape.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, ping_responder

SCAN_PAYLOAD: dict[str, Any] = {
    "tools": [
        {
            "name": "spawn_wave",
            "script": "res://scripts/waves.gd",
            "function": "spawn_wave",
            "description": "Spawn a wave of enemies.",
            "safety_class": "read_only",
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_item",
            "script": "res://scripts/loot.gd",
            "function": "add_item",
            "description": "Add an item to the loot table.",
            "safety_class": "destructive",
            "parameters": {
                "type": "object",
                "properties": {"item": {"type": "string"}},
                "required": ["item"],
                "additionalProperties": False,
            },
        },
    ],
    "rejected": [
        {
            "script": "res://scripts/bad.gd",
            "function": "loose",
            "reason": "untyped parameter 'x'",
            "line": 9,
        }
    ],
}


def _build() -> tuple[Any, FakeAddonConnection]:
    def responder(command: CommandEnvelope) -> ResponseEnvelope | None:
        if command.command == "cmd_scan_project_tools":
            return ResponseEnvelope.success(command.id, SCAN_PAYLOAD)
        if command.command == "cmd_run_project_tool":
            return ResponseEnvelope.success(
                command.id, {"result": {"script": command.params.get("script")}}
            )
        return ping_responder(command)

    fake = FakeAddonConnection(responder)
    config = ServerConfig(godot_project_dir="/tmp/project")
    bridge = Bridge(config.bridge, connector=connector_for(fake))
    return create_server(config, bridge=bridge), fake


def _sent_commands(fake: FakeAddonConnection) -> list[str]:
    return [
        CommandEnvelope.model_validate_json(raw).command for raw in fake.sent if raw.startswith("{")
    ]


async def test_scan_registers_project_tools_and_reports_rejections() -> None:
    server, fake = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool("godot_project_scan_tools", {})
        names = {tool.name for tool in await client.list_tools()}

    registered = {entry["name"] for entry in result.structured_content["registered"]}
    assert registered == {
        "godot_project_waves_spawn_wave",
        "godot_project_loot_add_item",
    }
    assert names >= registered
    assert result.structured_content["count"] == 2
    rejected = result.structured_content["rejected"]
    assert rejected[0]["script"] == "res://scripts/bad.gd"
    assert "untyped" in rejected[0]["reason"]
    assert "godot_project_bad_loose" not in names
    assert _sent_commands(fake).count("cmd_scan_project_tools") == 1


async def test_project_tools_are_gated_by_the_project_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        await client.call_tool("godot_project_scan_tools", {})
        await client.call_tool("godot_disable_toolset", {"category": "project"})
        names = {tool.name for tool in await client.list_tools()}
        refused = await client.call_tool(
            "godot_project_waves_spawn_wave", {"count": 1}, raise_on_error=False
        )

    assert "godot_project_waves_spawn_wave" not in names
    assert refused.is_error
    assert refused.structured_content["error"] == "PRECONDITION_FAILED"
    assert refused.structured_content["required"] == "toolset"


async def test_destructive_project_tool_requires_confirm() -> None:
    server, fake = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        await client.call_tool("godot_project_scan_tools", {})
        blocked = await client.call_tool(
            "godot_project_loot_add_item", {"item": "sword"}, raise_on_error=False
        )
        ran = await client.call_tool(
            "godot_project_loot_add_item", {"item": "sword", "confirm": True}
        )

    assert blocked.is_error
    assert blocked.structured_content["error"] == "PRECONDITION_FAILED"
    assert blocked.structured_content["required"] == "confirm"
    run_calls = [c for c in _sent_commands(fake) if c == "cmd_run_project_tool"]
    assert len(run_calls) == 1  # only the confirmed call reached the addon
    assert ran.structured_content["result"]["script"] == "res://scripts/loot.gd"


async def test_dry_run_previews_without_calling_the_addon() -> None:
    server, fake = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        await client.call_tool("godot_project_scan_tools", {})
        preview = await client.call_tool(
            "godot_project_loot_add_item",
            {"item": "sword", "confirm": True, "dry_run": True},
        )

    assert preview.structured_content["dry_run"] is True
    assert preview.structured_content["preview"]["args"] == {"item": "sword"}
    assert "cmd_run_project_tool" not in _sent_commands(fake)


async def test_mutating_project_tool_schema_gets_dry_run_and_confirm_only_where_needed() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        await client.call_tool("godot_project_scan_tools", {})
        tools = {tool.name: tool for tool in await client.list_tools()}

    read_only = tools["godot_project_waves_spawn_wave"]
    destructive = tools["godot_project_loot_add_item"]
    assert "dry_run" not in (read_only.input_schema.get("properties") or {})
    props = destructive.input_schema["properties"]
    assert "dry_run" in props and "confirm" in props
    assert destructive.meta["safety_class"] == "destructive"
    assert "confirm=True" in destructive.description
