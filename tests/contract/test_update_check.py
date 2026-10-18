"""Contract tests: version-drift notices + the opt-in update check (issue #629)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.command_map import BARE_TO_COMMAND
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from mcp_server.updates import LatestRelease, UpdateChecker
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio

ADDON_VER = "2026.09.30"  # deliberately older than the running server


def _responder() -> Callable[[CommandEnvelope], ResponseEnvelope | None]:
    base = make_addon_responder(godot_version="4.7")

    def respond(command: CommandEnvelope) -> ResponseEnvelope | None:
        if command.command == "cmd_get_addon_info":
            return ResponseEnvelope.success(
                command.id,
                {
                    "addon_version": ADDON_VER,
                    "godot_version": "4.7",
                    "commands": sorted(set(BARE_TO_COMMAND.values())),
                },
            )
        return base(command)

    return respond


def _server(
    config: ServerConfig | None = None,
    *,
    checker: UpdateChecker | None = None,
    addon: FakeAddonConnection | None = None,
) -> FastMCP:
    config = config or ServerConfig()
    addon = addon or FakeAddonConnection(_responder())
    bridge = Bridge(config.bridge, connector=connector_for(addon))
    return create_server(config, bridge=bridge, update_checker=checker)


async def _newer_release() -> LatestRelease | None:
    return LatestRelease("9999.01.01", "https://example.invalid/9999")


async def test_get_server_info_flags_addon_version_mismatch() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("godot_get_server_info", {})
    data = result.structured_content
    assert data["bridge"]["addon_version"] == ADDON_VER
    assert data["version_notice"] and "MISMATCH" in data["version_notice"]


async def test_health_check_reports_addon_version_and_notice() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("godot_health_check", {})
    data = result.structured_content
    assert data["bridge_connected"] is True
    assert data["addon_version"] == ADDON_VER
    assert "MISMATCH" in data["version_notice"]


async def test_check_for_updates_is_disabled_by_default() -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("godot_check_for_updates", {})
    data = result.structured_content
    assert data["enabled"] is False
    assert data["update_available"] is False
    assert "GODOT_MCP_CHECK_UPDATES" in (data.get("hint") or "")


async def test_check_for_updates_reports_a_newer_release_and_notifies_the_dock() -> None:
    addon = FakeAddonConnection(_responder())
    config = ServerConfig(check_updates=True)
    checker = UpdateChecker(enabled=True, fetcher=_newer_release)
    server = _server(config, checker=checker, addon=addon)
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool("godot_check_for_updates", {})
    data = result.structured_content
    assert data["enabled"] is True and data["update_available"] is True
    assert data["latest"] == "9999.01.01"
    # The dock gets the update line (fire-and-forget push, #629).
    assert any("cmd_update_available" in message for message in addon.sent)


async def test_get_server_info_surfaces_a_known_update_in_next_steps() -> None:
    checker = UpdateChecker(enabled=True, fetcher=_newer_release)
    server = _server(ServerConfig(check_updates=True), checker=checker)
    async with Client(server) as client:
        await client.call_tool("godot_check_for_updates", {})  # populates the cache
        result = await client.call_tool("godot_get_server_info", {})
    data = result.structured_content
    assert data["update"] is not None and data["update"]["update_available"] is True
    assert any("newer Godot Editor MCP" in step for step in data["next_steps"])
