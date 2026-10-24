"""Contract: consent tokens bind exact destructive args (#759)."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

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
        return ResponseEnvelope.success(
            command.id, {"is_open": True, "path": "res://main.tscn", "name": "Main"}
        )
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_delete_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": command.params.get("node_path"),
                "deleted": True,
                "receipt": {"status": "updated", "changes": [], "truncated": False},
            },
        )
    return make_addon_responder(godot_version="4.7.2-stable")(command)


def _server(
    *,
    config: ServerConfig | None = None,
    approval: ApprovalGate | None = None,
) -> FastMCP:
    config = config or ServerConfig()
    bridge = Bridge(
        config.bridge,
        connector=connector_for(FakeAddonConnection(_responder)),
    )
    return create_server(config, bridge=bridge, approval=approval)


async def _token(client: Client[Any], node_path: str = "Root/Gone") -> str:
    described = await client.call_tool(
        "godot_describe_tool",
        {"tool": "godot_scene_edit_delete_node", "args": {"node_path": node_path}},
    )
    payload = described.structured_content
    assert payload is not None
    assert payload["consent_required"] is True
    token = payload["token"]
    assert isinstance(token, str) and token
    return token


async def test_describe_mints_and_token_authorizes_the_exact_call() -> None:
    async with Client(_server(), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        token = await _token(client)
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "consent": token},
        )
    assert result.structured_content["deleted"] is True


async def test_changed_args_are_refused_with_a_describe_next_call() -> None:
    async with Client(_server(), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        token = await _token(client, "Root/A")
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/B", "consent": token},
            raise_on_error=False,
        )
    assert result.is_error
    payload = result.structured_content
    assert payload["error"] == "CONSENT_MISMATCH"
    assert payload["next_call"]["tool"] == "godot_describe_tool"
    assert payload["next_call"]["args"]["tool"] == "godot_scene_edit_delete_node"


async def test_token_replay_is_refused() -> None:
    async with Client(_server(), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        token = await _token(client)
        await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "consent": token},
        )
        replay = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "consent": token},
            raise_on_error=False,
        )
    assert replay.is_error
    assert replay.structured_content["error"] == "CONSENT_MISMATCH"


async def test_non_destructive_tools_need_no_consent() -> None:
    async with Client(_server(), mode="legacy") as client:
        result = await client.call_tool(
            "godot_describe_tool",
            {"tool": "godot_inspection_get_scene_tree", "args": {}},
        )
    assert result.structured_content["consent_required"] is False
    assert result.structured_content["token"] is None


async def test_webhook_approval_configured_requires_a_token() -> None:
    async def approve(url: str, request: Any, timeout: float) -> ApprovalResponse:
        return ApprovalResponse(approved=True)

    gate = ApprovalGate(webhook_url="http://approval.test", poster=approve)
    async with Client(_server(approval=gate), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "confirm": True},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "CONSENT_MISMATCH"
    assert result.structured_content["next_call"]["tool"] == "godot_describe_tool"


async def test_webhook_approval_is_bound_and_not_asked_twice() -> None:
    calls: list[Any] = []

    async def poster(url: str, request: Any, timeout: float) -> ApprovalResponse:
        calls.append(request)
        return ApprovalResponse(approved=True)

    gate = ApprovalGate(webhook_url="http://approval.test", poster=poster)
    async with Client(_server(approval=gate), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        token = await _token(client)
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "consent": token},
        )
    assert result.structured_content["deleted"] is True
    assert len(calls) == 1  # minted after approval; the call was precleared
    assert calls[0].params["node_path"] == "Root/Gone"
