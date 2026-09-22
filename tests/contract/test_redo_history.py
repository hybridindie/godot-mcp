"""Contract tests for the `godot_redo` + `godot_list_history` core tools (#529).

Mirror the `test_undo.py` suite: drive the real FastMCP server over the
in-memory client, backed by a fake addon peer with canned responses —
`godot_redo` forwards to ``cmd_redo`` (mutating, dry-run preview), and
`godot_list_history` (read-only) forwards to ``cmd_list_history``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _redo_responder(redone: int) -> Callable[[CommandEnvelope], ResponseEnvelope | None]:
    def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_redo":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "redone": redone,
                    "requested": cmd.params.get("count", 1),
                    "last_action": "Create Node",
                },
            )
        return None  # bootstrap commands auto-answered by the fake

    return _responder


def _history_responder(
    payload: dict[str, Any], command_name: str = "cmd_list_history"
) -> Callable[[CommandEnvelope], ResponseEnvelope | None]:
    def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == command_name:
            return ResponseEnvelope.success(cmd.id, payload)
        return None

    return _responder


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_godot_redo_forwards_cmd_redo_with_count() -> None:
    conn = FakeAddonConnection(responder=_redo_responder(redone=2))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_redo", {"count": 2})
    assert conn.last_command().command == "cmd_redo"
    assert conn.last_command().params == {"count": 2, "dry_run": False}
    assert result.structured_content["redone"] == 2
    assert result.structured_content["nothing_to_redo"] is False


async def test_godot_redo_dry_run_previews_without_redoing() -> None:
    def _preview(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_redo":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "dry_run": True,
                    "requested": 1,
                    "has_redo": True,
                    "would_redo_next": "Create Node",
                },
            )
        return None

    conn = FakeAddonConnection(responder=_preview)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_redo", {"dry_run": True})
    assert conn.last_command().params == {"count": 1, "dry_run": True}
    assert result.structured_content["would_redo_next"] == "Create Node"
    assert "nothing_to_redo" not in result.structured_content  # not added on a dry-run


async def test_godot_redo_reports_nothing_to_redo() -> None:
    conn = FakeAddonConnection(responder=_redo_responder(redone=0))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_redo", {})
    assert result.structured_content["redone"] == 0
    assert result.structured_content["nothing_to_redo"] is True


async def test_godot_redo_rejects_nonpositive_count() -> None:
    conn = FakeAddonConnection(responder=_redo_responder(redone=0))
    with pytest.raises(ToolError, match="count"):
        async with Client(_build(conn)) as client:
            await client.call_tool("godot_redo", {"count": 0})
    # cmd_redo was never sent (only bootstrap commands, if any, reached the fake)
    assert all(CommandEnvelope.model_validate_json(m).command != "cmd_redo" for m in conn.sent)


async def test_godot_list_history_returns_documented_fields() -> None:
    conn = FakeAddonConnection(
        responder=_history_responder(
            {
                "version": 7,
                "has_undo": True,
                "has_redo": False,
                "can_redo": False,
                "current_action": "Create Node",
                "depth": 2,
                "recent": ["Create Node", "Set Property"],
            }
        )
    )
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_list_history", {})
    assert conn.last_command().command == "cmd_list_history"
    sc = result.structured_content
    assert sc["has_undo"] is True
    assert sc["has_redo"] is False
    # #529 ticket field: can_redo is a documented alias of has_redo.
    assert sc["can_redo"] is False
    assert sc["current_action"] == "Create Node"
    assert sc["depth"] == 2
    assert sc["recent"] == [{"name": "Create Node"}, {"name": "Set Property"}]


async def test_godot_list_history_empty_history_is_zero_values() -> None:
    conn = FakeAddonConnection(
        responder=_history_responder(
            {
                "version": 0,
                "has_undo": False,
                "has_redo": False,
                "can_redo": False,
                "current_action": "",
                "depth": 0,
                "recent": [],
            }
        )
    )
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_list_history", {})
    sc = result.structured_content
    assert sc["depth"] == 0
    assert sc["recent"] == []
    assert sc["has_undo"] is False and sc["has_redo"] is False