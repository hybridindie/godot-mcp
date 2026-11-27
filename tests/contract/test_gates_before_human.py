"""Contract: a call that will be refused never reaches a human approver.

Toolset gating is the innermost middleware, and argument validation happens
in the tool, so a disabled tool or a malformed call still asks the human to
approve it before failing.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.safety import ApprovalGate
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(command.id, {"is_open": True, "path": "res://m.tscn"})
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    return make_addon_responder(godot_version="4.7.2-stable")(command)


def _server() -> Any:
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection(_responder)))
    return create_server(config, bridge=bridge, approval=ApprovalGate(require_approval=True))


def _recording_handler(asked: list[str]) -> Any:
    async def handler(message: str, response_type: Any, params: Any, ctx: Any) -> ElicitResult:
        asked.append(message)
        return ElicitResult(action="accept", content=response_type(approve=True))

    return handler


async def test_disabled_toolset_is_refused_before_asking_the_human() -> None:
    asked: list[str] = []
    async with Client(_server(), mode="auto", elicitation_handler=_recording_handler(asked)) as c:
        result = await c.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["required"] == "toolset"
    assert asked == []


async def test_undeclared_argument_is_refused_before_asking_the_human() -> None:
    asked: list[str] = []
    async with Client(_server(), mode="auto", elicitation_handler=_recording_handler(asked)) as c:
        await c.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        asked.clear()
        result = await c.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X", "nmae": "typo"},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "UNDECLARED_PARAMETER"
    assert asked == []
