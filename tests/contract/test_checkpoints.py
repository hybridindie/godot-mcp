"""Contract: undo checkpoints mark and restore a point in the scene history (#760)."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _server(state: dict[str, Any]) -> tuple[FastMCP, FakeAddonConnection]:
    def responder(command: Any) -> ResponseEnvelope | None:
        if command.command == "cmd_undo_state":
            return ResponseEnvelope.success(command.id, dict(state))
        if command.command == "cmd_undo":
            count = int(command.params.get("count", 1))
            state["current"] = max(0, state["current"] - count)
            return ResponseEnvelope.success(
                command.id, {"undone": count, "requested": count}
            )
        return make_addon_responder(godot_version="4.7.2-stable")(command)

    conn = FakeAddonConnection(responder)
    config = ServerConfig()
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge), conn


async def test_create_and_restore_undoes_to_the_marker() -> None:
    state = {
        "available": True,
        "current": 2,
        "count": 10,
        "scene_path": "res://main.tscn",
    }
    server, conn = _server(state)
    async with Client(server, mode="legacy") as client:
        checkpoint = await client.call_tool(
            "godot_checkpoint_create", {"label": "before edits"}
        )
        state["current"] = 5  # three more actions after the checkpoint
        restored = await client.call_tool(
            "godot_checkpoint_restore",
            {"checkpoint_id": checkpoint.structured_content["checkpoint_id"]},
        )
    assert checkpoint.structured_content["label"] == "before edits"
    assert checkpoint.structured_content["current_action"] == 2
    assert restored.structured_content["requested"] == 3
    assert restored.structured_content["undone"] == 3
    assert restored.structured_content["complete"] is True
    assert state["current"] == 2
    assert [c.command for c in _commands(conn)].count("cmd_undo") == 1


async def test_dry_run_does_not_touch_the_history() -> None:
    state = {"available": True, "current": 1, "count": 5, "scene_path": "res://m.tscn"}
    server, conn = _server(state)
    async with Client(server, mode="legacy") as client:
        checkpoint = await client.call_tool("godot_checkpoint_create", {})
        state["current"] = 4
        restored = await client.call_tool(
            "godot_checkpoint_restore",
            {"checkpoint_id": checkpoint.structured_content["checkpoint_id"], "dry_run": True},
        )
    assert restored.structured_content["requested"] == 3
    assert restored.structured_content["undone"] == 0
    assert restored.structured_content["dry_run"] is True
    assert "cmd_undo" not in [c.command for c in _commands(conn)]


async def test_restore_refuses_a_different_scene() -> None:
    state = {"available": True, "current": 0, "count": 2, "scene_path": "res://a.tscn"}
    server, _ = _server(state)
    async with Client(server, mode="legacy") as client:
        checkpoint = await client.call_tool("godot_checkpoint_create", {})
        state["scene_path"] = "res://b.tscn"
        result = await client.call_tool(
            "godot_checkpoint_restore",
            {"checkpoint_id": checkpoint.structured_content["checkpoint_id"]},
            raise_on_error=False,
        )
    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    hint = result.structured_content["hint"]
    assert "different" in hint or "belongs" in hint


async def test_restore_refuses_a_cleared_or_ahead_history() -> None:
    state = {"available": True, "current": 5, "count": 10, "scene_path": "res://m.tscn"}
    server, _ = _server(state)
    async with Client(server, mode="legacy") as client:
        checkpoint = await client.call_tool("godot_checkpoint_create", {})
        cp = checkpoint.structured_content["checkpoint_id"]
        state["count"] = 1  # cleared/replaced history
        cleared = await client.call_tool(
            "godot_checkpoint_restore", {"checkpoint_id": cp}, raise_on_error=False
        )
        state["count"] = 10
        state["current"] = 2  # behind the checkpoint
        ahead = await client.call_tool(
            "godot_checkpoint_restore", {"checkpoint_id": cp}, raise_on_error=False
        )
    assert cleared.structured_content["error"] == "PRECONDITION_FAILED"
    assert "stale" in cleared.structured_content["hint"]
    assert ahead.structured_content["error"] == "PRECONDITION_FAILED"
    assert "ahead" in ahead.structured_content["hint"]


def _commands(conn: FakeAddonConnection) -> list[Any]:
    from mcp_server.models.envelope import CommandEnvelope

    return [CommandEnvelope.model_validate_json(s) for s in conn.sent]
