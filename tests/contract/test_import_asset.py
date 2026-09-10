"""Contract tests for external asset import tools (issue #108).

All three tools live in a new ``asset_import`` toolset (gated off by default).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from unittest.mock import patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _is_scalar(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


# The fixture project's existing textures (paths the material tests reference).
# The probe models the real addon search: the glob matches file *names* only,
# so these must have distinct basenames for the tool's suffix check to resolve.
_FIXTURE_TEXTURES = [
    "res://tex/albedo.png",
    "res://tex/normal.png",
    "res://tex/a.png",
    "res://textures/metal.png",
    "res://tex/crystal.png",
    "res://tex/glow.png",
    "res://tex/rough.png",
    "res://tex/metallic.png",
]


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
        case "cmd_search_files":
            # Texture-existence probe: model the real addon semantics (Qodo #452
            # review) — the search recurses, but the glob matches file *names*
            # only (verified on Godot 4.7), so the tool globs the basename and
            # requires a match ending with the full requested res:// path. The
            # fixture project "has" every texture in _FIXTURE_TEXTURES (paths the
            # tests reference) plus anything whose basename contains "missing"
            # is absent — driving the NOT_FOUND path.
            glob = p.get("name_glob", "")
            if "missing" in glob:
                return ResponseEnvelope.success(cmd.id, {"matches": [], "truncated": False})
            return ResponseEnvelope.success(
                cmd.id, {"matches": list(_FIXTURE_TEXTURES), "truncated": False}
            )
        case "cmd_create_material_from_textures":
            # Mirror the addon's channel handling (#419/#428): scalars are noted
            # as "<channel>:scalar", emission auto-enables emission_enabled.
            channels = ["albedo", "normal", "roughness", "metallic", "ao", "emission"]
            set_channels: list[str] = []
            for c in channels:
                v = str(p.get(c, ""))
                if not v:
                    continue
                set_channels.append(c if not _is_scalar(v) else f"{c}:scalar")
            if str(p.get("emission", "")):
                set_channels.append("emission_enabled:scalar")
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "material_path": p.get("path", "res://materials/generated_mat.tres"),
                    "created": True,
                    "channels_set": set_channels,
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
    async with Client(server, mode="legacy") as client:
        assert "godot_asset_import_asset" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        names = {t.name for t in await client.list_tools()}
    assert {
        "godot_asset_import_asset",
        "godot_asset_import_create_material_from_textures",
        "godot_asset_import_get_status",
    } <= names


async def test_import_asset_success() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_asset",
            {"source": "res://temp/download.png", "target_path": "res://assets/download.png"},
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["target_path"] == "res://assets/download.png"
    assert result.structured_content["detected_type"] == "Texture2D"
    assert "cmd_import_asset" in _commands(conn)


async def test_import_asset_with_url_download_cleanup() -> None:
    """When source is a URL, the downloaded temporary file is cleaned up
    after the addon call.
    """
    server, conn = _build()
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    assert os.path.exists(tmp)

    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        with patch("mcp_server.tools.import_asset._download_url", return_value=tmp):
            result = await client.call_tool(
                "godot_asset_import_asset",
                {
                    "source": "https://example.com/img.png",
                    "target_path": "res://assets/img.png",
                },
            )
    assert result.structured_content["imported"] is True
    # The addon was called with the temp path; it should have been cleaned up.
    assert not os.path.exists(tmp)
    last = CommandEnvelope.model_validate_json(conn.sent[-1])
    assert last.params.get("source") == tmp


async def test_import_asset_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        dry = await client.call_tool(
            "godot_asset_import_asset",
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
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_create_material_from_textures",
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
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        dry = await client.call_tool(
            "godot_asset_import_create_material_from_textures",
            {"albedo": "res://tex/a.png", "dry_run": True},
        )
    assert dry.structured_content["dry_run"] is True
    assert dry.structured_content["created"] is False
    assert "cmd_create_material_from_textures" not in _commands(conn)


async def test_create_material_accepts_scalar_metallic_roughness() -> None:
    """#419: metallic/roughness are scalar floats on StandardMaterial3D — a numeric
    string must be accepted as a scalar (channel noted as `<channel>:scalar`), not
    treated as a texture path that aborts the whole material."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_create_material_from_textures",
            {
                "albedo": "res://textures/metal.png",
                "metallic": "0.7",
                "roughness": "0.45",
                "path": "res://materials/metal.tres",
            },
        )
    assert result.structured_content["created"] is True
    assert result.structured_content["channels_set"] == [
        "albedo",
        "roughness:scalar",
        "metallic:scalar",
    ]
    sent = CommandEnvelope.model_validate_json(conn.sent[-1])
    assert sent.params["metallic"] == "0.7"
    assert sent.params["roughness"] == "0.45"


async def test_create_material_dry_run_validates_params() -> None:
    """#419: a dry_run must run the same validation as the real run — a missing
    texture fails the preview instead of giving false confidence."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        with pytest.raises(ToolError, match="Texture not found for 'albedo'"):
            await client.call_tool(
                "godot_asset_import_create_material_from_textures",
                {"albedo": "res://missing/does_not_exist.png", "dry_run": True},
            )
    assert "cmd_create_material_from_textures" not in _commands(conn)


async def test_create_material_missing_texture_validates_in_dry_run() -> None:
    """#419: the same bad texture also fails the real run — validation parity."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        with pytest.raises(ToolError, match="RESOURCE_NOT_FOUND"):
            await client.call_tool(
                "godot_asset_import_create_material_from_textures",
                {"albedo": "res://missing/does_not_exist.png"},
            )


async def test_create_material_emission_enables_emission() -> None:
    """#428: providing an emission texture must leave the material emissive —
    emission_enabled defaults on with a white color; a half-set (texture wired,
    emission_enabled=false) renders black no matter the texture."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_search_files":
            return ResponseEnvelope.success(
                cmd.id, {"matches": list(_FIXTURE_TEXTURES), "truncated": False}
            )
        if cmd.command == "cmd_create_material_from_textures":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "material_path": cmd.params.get("path", "res://materials/generated_mat.tres"),
                    "created": True,
                    "channels_set": ["albedo", "emission", "emission_enabled:scalar"],
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_create_material_from_textures",
            {"albedo": "res://tex/crystal.png", "emission": "res://tex/glow.png"},
        )
    sc = result.structured_content
    assert sc["created"] is True
    assert "emission" in sc["channels_set"]
    # The pin for the half-set state: emission_enabled travels with the texture.
    assert "emission_enabled:scalar" in sc["channels_set"]


async def test_get_import_status() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_get_status", {"target_path": "res://assets/download.png"}
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["type"] == "Texture2D"
    assert "cmd_get_import_status" in _commands(conn)


async def test_import_asset_safety_class() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        tool = next(t for t in await client.list_tools() if t.name == "godot_asset_import_asset")
    assert tool.meta is not None and tool.meta.get("safety_class") == "mutating"


async def test_get_import_status_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        tool = next(
            t for t in await client.list_tools() if t.name == "godot_asset_import_get_status"
        )
    assert tool.meta is not None and tool.meta.get("safety_class") == "read_only"


# --- wait-for-scan support (issue #400) --------------------------------------


def _build_with(
    responder: Callable[[CommandEnvelope], ResponseEnvelope | None],
) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _status_response(cmd: CommandEnvelope, ready: bool) -> ResponseEnvelope:
    return ResponseEnvelope.success(
        cmd.id,
        {
            "imported": ready,
            "last_modified": "2026-06-09T12:00:00Z" if ready else None,
            "type": "Texture2D" if ready else None,
        },
    )


async def test_import_asset_wait_for_scan_polls_until_ready() -> None:
    status_calls = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_import_asset":
            return _responder(cmd)
        if cmd.command == "cmd_get_import_status":
            status_calls["n"] += 1
            return _status_response(cmd, ready=status_calls["n"] >= 3)
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    server, _ = _build_with(responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_asset",
            {
                "source": "res://temp/x.png",
                "target_path": "res://assets/x.png",
                "wait_for_scan": True,
            },
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["scan_complete"] is True
    assert status_calls["n"] == 3


async def test_import_asset_wait_for_scan_timeout_reports_incomplete() -> None:
    status_calls = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_import_asset":
            return _responder(cmd)
        if cmd.command == "cmd_get_import_status":
            status_calls["n"] += 1
            return _status_response(cmd, ready=False)
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    server, _ = _build_with(responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_asset",
            {
                "source": "res://temp/x.png",
                "target_path": "res://assets/x.png",
                "wait_for_scan": True,
                "timeout_ms": 400,
            },
        )
    assert result.structured_content["imported"] is True
    assert result.structured_content["scan_complete"] is False
    assert status_calls["n"] >= 1


async def test_import_asset_without_wait_does_not_poll() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_asset",
            {"source": "res://temp/x.png", "target_path": "res://assets/x.png"},
        )
    assert result.structured_content["scan_complete"] is False
    assert "cmd_get_import_status" not in _commands(conn)


async def test_dry_run_with_wait_for_scan_never_polls() -> None:
    """dry_run returns the preview before the bridge (and any polling) is touched."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_asset",
            {
                "source": "res://temp/x.png",
                "target_path": "res://assets/x.png",
                "dry_run": True,
                "wait_for_scan": True,
            },
        )
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["scan_complete"] is False
    assert _commands(conn) == []  # nothing sent: no import, no status polling


async def test_get_import_status_wait_ms_polls_until_ready() -> None:
    status_calls = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_import_status":
            status_calls["n"] += 1
            return _status_response(cmd, ready=status_calls["n"] >= 2)
        return _responder(cmd)

    server, _ = _build_with(responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "asset_import"})
        result = await client.call_tool(
            "godot_asset_import_get_status",
            {"target_path": "res://assets/x.png", "wait_ms": 1500},
        )
    assert result.structured_content["imported"] is True
    assert status_calls["n"] == 2
