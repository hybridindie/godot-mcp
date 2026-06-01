"""Contract tests for godot:// context resources (issue #11)."""

from __future__ import annotations

import json

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
        case "cmd_get_project_info":
            return ResponseEnvelope.success(cmd.id, {"name": "demo", "godot_version": "4.6.3"})
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://m.tscn"})
        case "cmd_get_scene_tree":
            return ResponseEnvelope.success(
                cmd.id, {"tree": {"name": "Main", "max_depth": cmd.params.get("max_depth")}}
            )
        case "cmd_get_selected_node":
            return ResponseEnvelope.success(cmd.id, {"selected": None})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_static_resources_are_listable() -> None:
    server, _ = _build()
    async with Client(server) as client:
        uris = {str(r.uri) for r in await client.list_resources()}
        templates = {t.uriTemplate for t in await client.list_resource_templates()}
    assert {
        "godot://project/info",
        "godot://scene/current",
        "godot://scene/tree",
        "godot://node/selected",
    } <= uris
    assert "godot://scene/tree/{max_depth}" in templates


async def test_resource_returns_valid_json() -> None:
    server, _ = _build()
    async with Client(server) as client:
        contents = await client.read_resource("godot://project/info")
    payload = json.loads(contents[0].text)
    assert payload["name"] == "demo"


async def test_scene_tree_template_passes_depth() -> None:
    server, conn = _build()
    async with Client(server) as client:
        contents = await client.read_resource("godot://scene/tree/2")
    payload = json.loads(contents[0].text)
    assert payload["tree"]["max_depth"] == 2


async def test_resource_failure_is_valid_json_error() -> None:
    # A bridge failure must still yield valid JSON carrying the structured error.
    def failing(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(cmd.id, "BRIDGE_DISCONNECTED", "Godot not connected.")

    conn = FakeAddonConnection(responder=failing)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        contents = await client.read_resource("godot://project/info")
    payload = json.loads(contents[0].text)
    assert payload["error"] == "BRIDGE_DISCONNECTED"


async def test_read_resource_fallback_tool() -> None:
    server, _ = _build()
    async with Client(server) as client:
        # The fallback tool is in `core`, so it's exposed by default.
        result = await client.call_tool("read_resource", {"uri": "godot://project/info"})
        payload = json.loads(result.data)
        assert payload["name"] == "demo"

        err = await client.call_tool(
            "read_resource", {"uri": "godot://bogus"}, raise_on_error=False
        )
    assert err.is_error
    assert "Unknown resource URI" in str(err.content)
