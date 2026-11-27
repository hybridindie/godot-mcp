"""Contract: argument coercion runs before every gate that reads arguments.

A stringified ``"dry_run": "false"`` is truthy to a gate that reads the raw
arguments, but coercion later turns it into ``False`` and the real call runs.
Consent (#759) and readiness (#762) must see the coerced value.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalResponse
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
    if command.command == "cmd_delete_node":
        return ResponseEnvelope.success(
            command.id, {"node_path": command.params["node_path"], "deleted": True}
        )
    if command.command == "cmd_create_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": f"{command.params['parent_path']}/{command.params['name']}",
                "created": True,
            },
        )
    return make_addon_responder(godot_version="4.7.2-stable")(command)


def _sent(conn: FakeAddonConnection) -> list[str]:
    return [json.loads(s).get("command", "") for s in conn.sent]


async def test_string_dry_run_false_still_requires_a_consent_token() -> None:
    async def approve(url: str, request: Any, timeout: float) -> ApprovalResponse:
        return ApprovalResponse(approved=True)

    gate = ApprovalGate(webhook_url="http://approval.test", poster=approve)
    conn = FakeAddonConnection(_responder)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    server = create_server(config, bridge=bridge, approval=gate)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "confirm": True, "dry_run": "false"},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "CONSENT_MISMATCH"
    assert "cmd_delete_node" not in _sent(conn)


async def test_string_dry_run_false_is_still_gated_on_readiness() -> None:
    conn = FakeAddonConnection(_responder)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn), clock=lambda: 1_000.0)
    server = create_server(config, bridge=bridge)
    async with Client(server, mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await conn.push({"command": "cmd_editor_status", "params": {"status": "importing"}})
        for _ in range(100):
            if bridge.editor_status == "importing":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError(
                f"status 'importing' never reached the bridge ({bridge.editor_status!r})"
            )
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "X", "dry_run": "false"},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "EDITOR_BUSY"
    assert "cmd_create_node" not in _sent(conn)


def test_coercion_is_registered_before_every_argument_reading_gate() -> None:
    from mcp_server.approval_middleware import ApprovalMiddleware
    from mcp_server.coercion_middleware import ArgumentCoercionMiddleware
    from mcp_server.consent_middleware import ConsentMiddleware
    from mcp_server.readiness_middleware import ReadinessMiddleware

    server = create_server(ServerConfig())
    order = [type(m) for m in server.middleware]
    coerce = order.index(ArgumentCoercionMiddleware)
    for gate in (ReadinessMiddleware, ConsentMiddleware, ApprovalMiddleware):
        assert coerce < order.index(gate), f"{gate.__name__} reads raw arguments"
