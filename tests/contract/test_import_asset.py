"""Contract tests for external asset import tools (issue #108).

All three tools live in a new ``asset_import`` toolset (gated off by default).
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
        case "cmd_import_asset":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "imported": True,
                    "target_path": p["target_path"],
                    "detected_type": "Texture2D",
                },
            )
        case "cmd_create_material_from_textures":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "material_path": p.get("path", "res://materials/generated_mat.tres"),
                    "created": True,
                    "channels_set": ["albedo", "normal"],
                },
            )
        case "cmd_get_import_status":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "imported": True,
                    "last_modified": "2026-06-09T12:00:00Z",
                    "type": "Texture2D",
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_asset_import_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "import_asset" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        names = {t.name for t in await client.list_tools()}
    assert {"import_asset", "create_material_from_textures", "get_import_status"} <= names


async def test_import_asset_success() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "import_asset",
            {"source": "res://temp/download.png", "target_path": "res://assets/download.png"},
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["target_path"] == "res://assets/download.png"
    assert result.structured_content["detected_type"] == "Texture2D"
    assert "cmd_import_asset" in _commands(conn)


async def test_import_asset_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        dry = await client.call_tool(
            "import_asset",
            {
                "source": "https://example.com/img.png",
                "target_path": "res://assets/img.png",
                "dry_run": True,
            },
        )
    assert dry.structured_content["dry_run"] is True
    assert dry.structured_content["imported"] is False
    assert "cmd_import_asset" not in _commands(conn)


async def test_create_material_from_textures() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "create_material_from_textures",
            {
                "albedo": "res://tex/albedo.png",
                "normal": "res://tex/normal.png",
                "path": "res://materials/hero.tres",
            },
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["material_path"] == "res://materials/hero.tres"
    assert result.structured_content["channels_set"] == ["albedo", "normal"]
    assert "cmd_create_material_from_textures" in _commands(conn)


async def test_create_material_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        dry = await client.call_tool(
            "create_material_from_textures",
            {"albedo": "res://tex/a.png", "dry_run": True},
        )
    assert dry.structured_content["dry_run"] is True
    assert dry.structured_content["created"] is False
    assert "cmd_create_material_from_textures" not in _commands(conn)


async def test_get_import_status() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "get_import_status", {"target_path": "res://assets/download.png"}
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["type"] == "Texture2D"
    assert "cmd_get_import_status" in _commands(conn)


async def test_import_asset_safety_class() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        tool = next(t for t in await client.list_tools() if t.name == "import_asset")
    assert tool.meta is not None and tool.meta.get("safety_class") == "mutating"


async def test_get_import_status_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "asset_import"})
        tool = next(t for t in await client.list_tools() if t.name == "get_import_status")
    assert tool.meta is not None and tool.meta.get("safety_class") == "read_only"
