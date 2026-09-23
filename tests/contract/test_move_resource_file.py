"""Contract tests for move/rename project file with dependency remap (issue #532).

Drive the real FastMCP server over the in-memory client with a fake addon peer:
the tool routes to cmd_move_resource_file, validates res:// paths server-side,
returns typed envelopes (updated_refs + honest undoable), honors dry_run with a
preview of the referencing files, and surfaces the structured refusals.
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


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_move_resource_file":
            if p.get("preview"):
                if p.get("path") == "res://missing.gd":
                    return ResponseEnvelope.failure(
                        cmd.id, "RESOURCE_NOT_FOUND", "No file at 'res://missing.gd'.", "path"
                    )
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "old_path": p["path"],
                        "new_path": p["new_path"],
                        "updated_refs": [
                            {"file": "res://main.tscn", "count": 2},
                            {"file": "res://player.gd", "count": 1},
                        ],
                        "moved": False,
                        "undoable": False,
                        "hint": (
                            "A file move is not UndoRedo-tracked; reverse it with a second "
                            "move_file(old→new) or version control."
                        ),
                    },
                )
            if p.get("path") == "res://missing.gd":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No file at 'res://missing.gd'.", "path"
                )
            if p.get("new_path") == "res://exists.gd":
                return ResponseEnvelope.failure(
                    cmd.id,
                    "VALIDATION_ERROR",
                    "A file already exists at 'res://exists.gd'. Move elsewhere (or delete the "
                    "existing file first).",
                    "new_path",
                )
            if p.get("path") == "res://dirty.tscn":
                return ResponseEnvelope.failure(
                    cmd.id,
                    "PRECONDITION_FAILED",
                    "'res://dirty.tscn' is open and has unsaved changes — moving it now would "
                    "clobber the in-memory copy. Call save_scene first, then move.",
                    "scene_saved",
                )
            if p.get("path") == "res://outside.gd":
                return ResponseEnvelope.failure(
                    cmd.id,
                    "VALIDATION_ERROR",
                    "'new_path' escapes the project root (res://). Got: 'res://../etc/gd'",
                    "new_path",
                )
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "old_path": p["path"],
                    "new_path": p["new_path"],
                    "updated_refs": [{"file": "res://main.tscn", "count": 1}],
                    "moved": True,
                    "undoable": False,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_mutating_in_project_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_project_move_file" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        tools = {t.name: t for t in await client.list_tools()}
    tool = tools["godot_project_move_file"]
    assert tool.meta["safety_class"] == "mutating"
    assert tool.annotations is not None and tool.annotations.read_only_hint is False


async def test_move_routes_params_and_returns_refs() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://player.gd", "new_path": "res://player_controller.gd"},
        )
    sc = result.structured_content
    assert sc["moved"] is True
    assert sc["old_path"] == "res://player.gd"
    assert sc["new_path"] == "res://player_controller.gd"
    assert sc["updated_refs"] == [{"file": "res://main.tscn", "count": 1}]
    assert sc["undoable"] is False
    params = conn.last_command().params
    assert params["path"] == "res://player.gd"
    assert params["new_path"] == "res://player_controller.gd"


async def test_move_dry_run_previews_refs() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://player.gd", "new_path": "res://player_controller.gd", "dry_run": True},
        )
    sc = result.structured_content
    assert sc["dry_run"] is True
    assert sc["moved"] is False
    assert len(sc["updated_refs"]) == 2
    assert sc["undoable"] is False
    # The preview reached the addon with preview=True (no real move dispatched).
    assert conn.last_command().params["preview"] is True


async def test_move_rejects_non_res_path() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        for bad in ("user://a.gd", "C:/a.gd", "a.gd"):
            result = await client.call_tool(
                "godot_project_move_file",
                {"path": bad, "new_path": "res://b.gd"},
                raise_on_error=False,
            )
            assert result.is_error, f"path={bad!r} must be refused"


async def test_move_rejects_path_traversal() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://a.gd", "new_path": "res://../outside.gd"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "escapes the project root" in str(result.content)


async def test_move_missing_source_is_structured_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://missing.gd", "new_path": "res://b.gd"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_move_existing_destination_is_structured_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://a.gd", "new_path": "res://exists.gd"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "already exists" in str(result.content)


async def test_move_unsaved_open_scene_is_precondition_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_move_file",
            {"path": "res://dirty.tscn", "new_path": "res://clean.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "PRECONDITION_FAILED" in str(result.content)