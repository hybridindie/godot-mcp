"""Contract tests for the `godot_undo` core tool (S4).

Drive the real FastMCP server over the in-memory client, backed by a fake addon
peer with canned responses: verify the tool forwards to ``cmd_undo`` with the
right params, maps the JSON-safe response through (adding ``nothing_to_undo``),
previews on ``dry_run``, and rejects ``count < 1`` pre-bridge.
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


def _undo_responder(undone: int):
    def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_undo":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "undone": undone,
                    "requested": cmd.params.get("count", 1),
                    "last_action": "Create Node",
                },
            )
        return None  # bootstrap commands (cmd_ping/cmd_get_project_info) auto-answered by the fake

    return _responder


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_godot_undo_forwards_cmd_undo_with_count() -> None:
    conn = FakeAddonConnection(responder=_undo_responder(undone=2))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {"count": 2})
    assert conn.last_command().command == "cmd_undo"
    assert conn.last_command().params == {"count": 2, "dry_run": False}
    assert result.structured_content["undone"] == 2
    assert result.structured_content["nothing_to_undo"] is False


async def test_godot_undo_dry_run_previews_without_undoing() -> None:
    def _preview(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_undo":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "dry_run": True,
                    "requested": 1,
                    "has_undo": True,
                    "would_undo_next": "Create Node",
                },
            )
        return None

    conn = FakeAddonConnection(responder=_preview)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {"dry_run": True})
    assert conn.last_command().params == {"count": 1, "dry_run": True}
    assert result.structured_content["would_undo_next"] == "Create Node"
    assert "nothing_to_undo" not in result.structured_content  # not added on a dry-run


async def test_godot_undo_reports_nothing_to_undo() -> None:
    conn = FakeAddonConnection(responder=_undo_responder(undone=0))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {})
    assert result.structured_content["undone"] == 0
    assert result.structured_content["nothing_to_undo"] is True
