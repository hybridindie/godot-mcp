"""Contract: structured, recoverable tool errors (#757).

``next_call`` (a fully-formed follow-up call) and the accepted-parameter list
reach the client in the error result's ``structuredContent``; the text content
still carries the same message for clients that only render text.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import NextCall, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _server(responder: Any | None = None) -> FastMCP:
    config = ServerConfig()
    responder = responder or make_addon_responder(godot_version="4.7.2-stable")
    bridge = Bridge(
        config.bridge,
        connector=connector_for(FakeAddonConnection(responder)),
    )
    return create_server(config, bridge=bridge)


def _no_scene_responder(command: Any) -> ResponseEnvelope | None:
    base = make_addon_responder(godot_version="4.7.2-stable")
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": False})
    return base(command)


async def test_disabled_toolset_carries_enable_next_call() -> None:
    async with Client(_server(), mode="legacy") as client:
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["error"] == "PRECONDITION_FAILED"
    assert payload["required"] == "toolset"
    assert payload["next_call"] == {
        "tool": "godot_enable_toolset",
        "args": {"category": "scene_edit"},
        "reason": "enable the 'scene_edit' toolset",
    }
    assert "not enabled" in str(result.content)


async def test_precondition_carries_a_recovery_call() -> None:
    async with Client(_server(_no_scene_responder), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["error"] == "PRECONDITION_FAILED"
    assert payload["required"] == "active_scene"
    assert payload["next_call"]["tool"] == "godot_inspection_list_scenes"
    assert payload["next_call"]["args"] == {}


async def test_undeclared_parameter_is_rejected_with_a_corrected_call() -> None:
    async with Client(_server(), mode="legacy") as client:
        result = await client.call_tool(
            "godot_inspection_get_node_properties",
            {"node_path": ".", "node_pathh": "Player"},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["error"] == "UNDECLARED_PARAMETER"
    assert payload["hint"].startswith("Unknown parameter 'node_pathh'")
    assert "node_path" in payload["hint"]
    # The near-miss is renamed in a ready-to-send call.
    assert payload["next_call"]["tool"] == "godot_inspection_get_node_properties"
    assert payload["next_call"]["args"] == {"node_path": "Player"}


async def test_addon_next_call_passes_through_the_bridge_envelope() -> None:
    def responder(command: Any) -> ResponseEnvelope | None:
        base = make_addon_responder(godot_version="4.7.2-stable")
        if command.command == "cmd_node_exists":
            return ResponseEnvelope.success(command.id, {"exists": True})
        if command.command == "cmd_set_node_property":
            return ResponseEnvelope.failure(
                command.id,
                "VALIDATION_ERROR",
                "Node has no property 'nodepath'.",
                next_call=NextCall(
                    tool="godot_scene_edit_set_node_property",
                    args={"node_path": ".", "property": "nodepath"},
                    reason="retry with the corrected property",
                ),
            )
        return base(command)

    async with Client(_server(responder), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": ".", "property": "nodepath", "value": 1},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["next_call"]["tool"] == "godot_scene_edit_set_node_property"
    assert payload["next_call"]["reason"] == "retry with the corrected property"
