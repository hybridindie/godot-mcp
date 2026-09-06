"""Contract tests for project scaffold tool (issue #112, reframed).

A single tool -- ``scaffold_project`` -- creates a structured project skeleton
(directory layout, project settings, autoloads, root scene) without shipping
code snippets or copyrighted assets.
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
        case "cmd_scaffold_project":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "created": True,
                    "paths_created": [
                        "res://scenes/",
                        "res://scripts/",
                        "res://assets/",
                        f"res://scenes/{p.get('main_scene', 'main')}.tscn",
                    ],
                    "autoloads_registered": ["GameState"],
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_project_scaffold_toolset() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_project_scaffold" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        names = {t.name for t in await client.list_tools()}
    assert "godot_project_scaffold" in names


async def test_scaffold_project_success() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        result = await client.call_tool(
            "godot_project_scaffold",
            {
                "type": "2d_platformer",
                "project_name": "JumpQuest",
                "confirm": True,
            },
        )
    assert result.structured_content["created"] is True
    assert "res://scenes/" in result.structured_content["paths_created"]
    assert "GameState" in result.structured_content["autoloads_registered"]
    assert "cmd_scaffold_project" in _commands(conn)


async def test_scaffold_forwards_confirm_to_addon() -> None:
    # #409: the addon re-gates destructively on params.confirm; the tool must
    # forward the caller's confirm flag in the bridge envelope, or the addon
    # rejects the very call the server-side gate already approved.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        await client.call_tool(
            "godot_project_scaffold",
            {"type": "3d_fps", "project_name": "Shooter", "confirm": True},
        )
    last = CommandEnvelope.model_validate_json(conn.sent[-1])
    assert last.params.get("confirm") is True


async def test_scaffold_project_requires_confirm() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        with pytest.raises(Exception) as exc:
            await client.call_tool(
                "godot_project_scaffold",
                {"type": "3d_fps", "project_name": "Shooter"},
            )
    assert "confirm" in str(exc.value).lower() or "PRECONDITION_FAILED" in str(exc.value)
    assert "cmd_scaffold_project" not in _commands(conn)


async def test_scaffold_project_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        dry = await client.call_tool(
            "godot_project_scaffold",
            {
                "type": "visual_novel",
                "project_name": "Story",
                "confirm": True,
                "dry_run": True,
            },
        )
    assert dry.structured_content["dry_run"] is True
    assert dry.structured_content["created"] is False
    assert "cmd_scaffold_project" not in _commands(conn)


async def test_scaffold_project_safety_class() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        tool = next(t for t in await client.list_tools() if t.name == "godot_project_scaffold")
    assert tool.meta is not None and tool.meta.get("safety_class") == "destructive"


async def test_scaffold_project_defaults() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "project_scaffold"})
        await client.call_tool(
            "godot_project_scaffold",
            {"type": "top_down_rpg", "project_name": "RPG", "confirm": True},
        )
    last = CommandEnvelope.model_validate_json(conn.sent[-1])
    assert last.params.get("main_scene", "main") == "main"
