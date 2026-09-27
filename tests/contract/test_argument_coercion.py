"""Contract tests: stringified JSON arguments survive to the bridge as real objects.

Reproduces the client-side failure mode seen in the wild (opencode serializing
dict/list params as JSON strings): without the coercion middleware, pydantic
rejects the call before the tool body runs. With it, the addon receives proper
dicts and bool assertions compare like-typed values.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _last_params(conn: FakeAddonConnection, command: str) -> dict[str, Any]:
    for raw in reversed(conn.sent):
        env = CommandEnvelope.model_validate_json(raw)
        if env.command == command:
            return env.params
    raise AssertionError(f"{command} was never sent")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        match cmd.command:
            case "cmd_node_exists":
                return ResponseEnvelope.success(cmd.id, {"exists": True})
            case "cmd_create_resource":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "resource_path": cmd.params["resource_path"],
                        "type": cmd.params["type"],
                        "created": True,
                    },
                )
            case "cmd_monitor_property":
                return ResponseEnvelope.success(cmd.id, {"monitoring": True})
            case "cmd_read_property":
                # #571: assert_node_state reads via the dedicated one-shot read now.
                return ResponseEnvelope.success(
                    cmd.id, {"ready": True, "value": False, "error": ""}
                )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_create_resource_accepts_stringified_properties() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "godot_resources_edit_create_resource",
            {
                "type": "StandardMaterial3D",
                "resource_path": "res://materials3d/mat_wall.tres",
                "properties": '{"albedo_color": "#ff6a2b"}',
            },
        )
    assert result.is_error is False
    params = _last_params(conn, "cmd_create_resource")
    assert params["properties"] == {"albedo_color": "#ff6a2b"}


async def test_dry_run_stringified_boolean_short_circuits() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "godot_resources_edit_create_resource",
            {
                "type": "StandardMaterial3D",
                "resource_path": "res://x.tres",
                "dry_run": "True",
            },
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_create_resource" not in [
        CommandEnvelope.model_validate_json(s).command for s in conn.sent
    ]


async def test_assert_accepts_stringified_boolean_expected() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        result = await client.call_tool(
            "godot_testing_assert_node_state",
            {
                "node_path": "/root/Main/HUD/GameOverLabel",
                "property": "visible",
                "expected": "False",
                "op": "==",
            },
        )
    content = result.structured_content
    assert content["actual"] is False
    assert content["passed"] is True


async def test_stringified_events_array_reaches_addon_as_objects() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_play_input_sequence":
            return ResponseEnvelope.success(
                cmd.id,
                {"sent": True, "kind": "sequence", "count": len(cmd.params["events"])},
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input"})
        result = await client.call_tool(
            "godot_input_play_sequence",
            {
                "events": '[{"type": "action", "action": "jump", "pressed": "True"}]',
                "delay_ms": "50",
            },
        )
    assert result.is_error is False
    params = _last_params(conn, "cmd_play_input_sequence")
    assert params["events"] == [{"type": "action", "action": "jump", "pressed": True}]
