"""Contract tests for project & filesystem tools (issue #32)."""

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
        case "cmd_get_filesystem_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "tree": {
                        "name": "res://",
                        "path": "res://",
                        "type": "directory",
                        "children": [{"name": "a.gd", "path": "res://a.gd", "type": "file"}],
                    }
                },
            )
        case "cmd_search_files":
            return ResponseEnvelope.success(
                cmd.id, {"matches": ["res://a.gd", "res://b.gd"], "truncated": False}
            )
        case "cmd_get_setting":
            exists = p["name"] == "application/config/name"
            return ResponseEnvelope.success(
                cmd.id,
                {"name": p["name"], "value": "demo" if exists else None, "exists": exists},
            )
        case "cmd_set_setting":
            return ResponseEnvelope.success(
                cmd.id, {"name": p["name"], "value": p["value"], "set": True}
            )
        case "cmd_path_to_uid":
            return ResponseEnvelope.success(cmd.id, {"path": p["path"], "uid": "uid://abc123"})
        case "cmd_uid_to_path":
            return ResponseEnvelope.success(cmd.id, {"uid": p["uid"], "path": "res://a.gd"})
        case "cmd_delete_resource_file":
            if p["path"] == "res://missing.tres":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No file at 'res://missing.tres'."
                )
            return ResponseEnvelope.success(
                cmd.id, {"path": p["path"], "deleted": True, "had_uid": True}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_project_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_project_get_filesystem_tree" not in {
            t.name for t in await client.list_tools()
        }
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        names = {t.name for t in await client.list_tools()}
    expected = {
        "godot_project_get_filesystem_tree",
        "godot_project_search_files",
        "godot_project_get_setting",
        "godot_project_set_setting",
        "godot_project_resolve_uid",
    }
    assert expected <= names


async def test_filesystem_tree_and_search() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        tree = await client.call_tool("godot_project_get_filesystem_tree", {"directory": "res://"})
        found = await client.call_tool("godot_project_search_files", {"name_glob": "*.gd"})
    assert tree.structured_content["tree"]["children"][0]["name"] == "a.gd"
    assert found.structured_content["matches"] == ["res://a.gd", "res://b.gd"]


async def test_get_setting_exists_and_missing() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        present = await client.call_tool(
            "godot_project_get_setting", {"name": "application/config/name"}
        )
        missing = await client.call_tool("godot_project_get_setting", {"name": "nope/key"})
    assert present.structured_content == {
        "name": "application/config/name",
        "value": "demo",
        "exists": True,
    }
    assert missing.structured_content["exists"] is False


async def test_set_setting_safety_and_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        tool = next(t for t in await client.list_tools() if t.name == "godot_project_set_setting")
        assert tool.meta is not None and tool.meta.get("safety_class") == "mutating"
        dry = await client.call_tool(
            "godot_project_set_setting", {"name": "x/y", "value": 1, "dry_run": True}
        )
    assert dry.structured_content["dry_run"] is True
    assert "cmd_set_setting" not in _commands(conn)


async def test_resolve_uid_both_directions() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        from_path = await client.call_tool("godot_project_resolve_uid", {"value": "res://a.gd"})
        from_uid = await client.call_tool("godot_project_resolve_uid", {"value": "uid://abc123"})
    assert from_path.structured_content["uid"] == "uid://abc123"
    assert from_uid.structured_content["path"] == "res://a.gd"
    assert "cmd_path_to_uid" in _commands(conn) and "cmd_uid_to_path" in _commands(conn)


async def test_delete_resource_file_requires_confirm() -> None:
    # Destructive: without confirm (and not a dry_run) it must refuse, not delete.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        result = await client.call_tool(
            "godot_project_delete_resource_file", {"path": "res://gen.tres"}, raise_on_error=False
        )
    assert result.is_error
    assert "confirm" in str(result.content)
    assert "cmd_delete_resource_file" not in _commands(conn)


async def test_delete_resource_file_dry_run_previews() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        dry = await client.call_tool(
            "godot_project_delete_resource_file", {"path": "res://gen.tres", "dry_run": True}
        )
    assert dry.structured_content["deleted"] is False
    assert dry.structured_content["dry_run"] is True
    assert "cmd_delete_resource_file" not in _commands(conn)


async def test_delete_resource_file_confirmed_deletes() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        done = await client.call_tool(
            "godot_project_delete_resource_file", {"path": "res://gen.tres", "confirm": True}
        )
    data = done.structured_content
    assert data["deleted"] is True and data["had_uid"] is True
    assert "cmd_delete_resource_file" in _commands(conn)


async def test_delete_resource_file_rejects_escape() -> None:
    # res:// containment (#205): a traversal/non-res path is rejected before the bridge.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        escape = await client.call_tool(
            "godot_project_delete_resource_file",
            {"path": "res://../secret.tres", "confirm": True},
            raise_on_error=False,
        )
        absolute = await client.call_tool(
            "godot_project_delete_resource_file",
            {"path": "/etc/passwd", "confirm": True},
            raise_on_error=False,
        )
    assert escape.is_error and absolute.is_error
    assert "cmd_delete_resource_file" not in _commands(conn)


async def test_delete_resource_file_is_destructive() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_project_delete_resource_file"].meta["safety_class"] == "destructive"
