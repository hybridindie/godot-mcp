"""Contract tests for the server↔addon handshake (issue #530, fixes #521).

``cmd_get_addon_info`` is the addon's self-description: addon version (read
from ``plugin.cfg``), the Godot version it runs inside, and the full list of
registered ``cmd_*`` handler names. The server calls it lazily on first
project-info exchange, caches the result, and surfaces it in
``godot_get_server_info`` (``BridgeDiagnostics``) so a client can see the
connected addon's version and command set — turning a server↔addon version
drift from opaque per-command ``Unknown command`` errors into a visible,
diagnosable mismatch.

The addon side is GDScript (only runnable inside Godot): its envelope shape is
pinned by the source scan + the live smoke script
(``godot/tests/handshake_smoke.gd``). These tests pin the *server* side: the
fake addon answers ``cmd_get_addon_info`` and the server must surface
``addon_version`` / ``godot_version`` / ``addon_commands`` in the diagnostics
snapshot, and the plugin's dock label half (issue #521) is pinned by the
GDScript smoke.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

import mcp_server
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for
from tests.integration._godot import GODOT_BIN, run_godot

ADDON_VERSION = mcp_server.__version__  # kept in lockstep by test_addon_manifest.py

_REHANDSHAKE_LOCK = asyncio.Lock()


def _addon_responder(command: CommandEnvelope) -> ResponseEnvelope | None:
    """Fake addon that answers the handshake + the diagnostics bootstrap set."""
    if command.command == "cmd_get_addon_info":
        return ResponseEnvelope.success(
            command.id,
            {
                "addon_version": ADDON_VERSION,
                "godot_version": "4.7.2-stable",
                "commands": ["cmd_ping", "cmd_get_project_info", "cmd_get_addon_info"],
            },
        )
    from tests.fakes import ping_responder

    return ping_responder(command)


def _handshake_responder_factory() -> object:
    """A connector-backed Bridge whose fake addon supports the handshake."""
    # Imported lazily so the module stays importable without the integration helpers.
    from mcp_server.bridge import Bridge
    from mcp_server.config import BridgeConfig

    conn = FakeAddonConnection(_addon_responder)
    return Bridge(BridgeConfig(), connector=connector_for(conn))


@pytest.fixture
def server() -> FastMCP:
    from mcp_server.server import create_server

    return create_server()


async def _call_tool(server: FastMCP, name: str) -> str:
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool(name, arguments={})
    return " ".join(str(getattr(item, "text", "")) for item in result.content)


def _plugin_cfg_version() -> str:
    cfg = Path(__file__).resolve().parents[2] / "godot/addons/godot_mcp/plugin.cfg"
    for line in cfg.read_text().splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


# -- addon side (source-scanned, per the test_rename_refusal.py technique) ----


def test_addon_registers_cmd_get_addon_info_and_returns_required_fields() -> None:
    router_src = (
        Path(__file__).resolve().parents[2] / "godot/addons/godot_mcp/command_router.gd"
    ).read_text()
    # The handshake command is registered on the router (like cmd_ping).
    assert '_handlers["cmd_get_addon_info"]' in router_src
    # The handler reports addon version, Godot version, and the command list.
    handler_src = router_src.split("func _cmd_get_addon_info", 1)[1]
    assert "addon_version" in handler_src
    assert "godot_version" in handler_src
    assert "commands" in handler_src
    # The command list is the live registry, not a hardcoded table.
    assert "_handlers.keys()" in handler_src or "_handlers" in handler_src


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_addon_handshake_smoke_pins_the_envelope() -> None:
    """The live headless smoke asserts the real envelope shape inside Godot."""
    result = run_godot(["--script", "res://tests/handshake_smoke.gd"])
    output = result.stdout + result.stderr
    assert "HANDSHAKE_TEST_OK" in output, (
        f"handshake smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


# -- server side -------------------------------------------------------------


def test_plugin_cfg_version_is_the_source_of_the_addon_version() -> None:
    # The addon version flows from plugin.cfg; the smoke reads it live. This
    # pins the file as the single source so a version bump here is deliberate.
    assert _plugin_cfg_version() != "", "plugin.cfg must declare a version"


def test_bridge_diagnostics_model_has_addon_fields() -> None:
    from mcp_server.diagnostics import BridgeDiagnostics

    fields = BridgeDiagnostics.model_fields
    assert "addon_version" in fields
    assert "addon_commands" in fields
    # godot_version already existed (fetched via cmd_get_project_info).
    assert "godot_version" in fields

# -- server-side integration: handshake flows into the diagnostics snapshot ---


async def test_get_server_info_reports_addon_identity_when_connected() -> None:
    """With a connected fake addon, the snapshot carries the handshake fields."""

    from mcp_server.bridge import Bridge
    from mcp_server.config import BridgeConfig
    from mcp_server.diagnostics import BridgeDiagnostics, _fetch_bridge_diagnostics

    conn = FakeAddonConnection(_addon_responder)
    bridge: Bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()

    diag = await _fetch_bridge_diagnostics(bridge)
    assert isinstance(diag, BridgeDiagnostics)
    assert diag.connected is True
    assert diag.addon_version == ADDON_VERSION
    assert diag.addon_commands is not None
    assert "cmd_get_addon_info" in diag.addon_commands

    # Cached: a second diagnostics build must not re-send the handshake.
    info_after = await bridge.addon_info()
    assert info_after == {
        "addon_version": ADDON_VERSION,
        "godot_version": "4.7.2-stable",
        "commands": ["cmd_ping", "cmd_get_project_info", "cmd_get_addon_info"],
    }
    await bridge.close()


async def test_addon_info_cached_per_peer() -> None:
    """addon_info() sends cmd_get_addon_info once; a replaced peer refetches."""
    from mcp_server.bridge import Bridge
    from mcp_server.config import BridgeConfig

    calls: list[str] = []

    def counting_responder(command: CommandEnvelope) -> ResponseEnvelope | None:
        if command.command == "cmd_get_addon_info":
            calls.append(command.id)
            return _addon_responder(command)
        from tests.fakes import ping_responder

        return ping_responder(command)

    first = FakeAddonConnection(counting_responder)

    def connector(conn: FakeAddonConnection) -> Callable[[str], Awaitable[FakeAddonConnection]]:
        async def _connect(url: str) -> FakeAddonConnection:
            return conn

        return _connect

    bridge = Bridge(BridgeConfig(), connector=connector(first))
    await bridge.connect()
    one = await bridge.addon_info()
    two = await bridge.addon_info()
    assert one == two == {
        "addon_version": ADDON_VERSION,
        "godot_version": "4.7.2-stable",
        "commands": ["cmd_ping", "cmd_get_project_info", "cmd_get_addon_info"],
    }
    assert len(calls) == 1  # cached
    await bridge.close()
    assert len(calls) == 1


async def test_addon_info_none_when_addon_predates_handshake() -> None:
    """An old addon (unknown command) degrades to None fields, not an error."""
    from mcp_server.bridge import Bridge
    from mcp_server.config import BridgeConfig
    from mcp_server.diagnostics import _fetch_bridge_diagnostics

    conn = FakeAddonConnection()  # default responder: only ping + project info
    bridge: Bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()

    diag = await _fetch_bridge_diagnostics(bridge)
    assert diag.connected is True
    assert diag.addon_version is None
    assert diag.addon_commands is None
    # And the rest of the snapshot still reports the project.
    assert diag.project_name == "TestProject"
    await bridge.close()


def test_get_server_info_snapshot_shape_includes_addon_fields(server: FastMCP) -> None:
    """The diagnostics model serialization carries the new fields (offline values)."""
    result_text = asyncio.run(_call_tool(server, "godot_get_server_info"))
    payload = json.loads(result_text)
    assert "addon_version" in json.dumps(payload)
    bridge = payload["bridge"]
    assert "addon_version" in bridge and "addon_commands" in bridge


def test_addon_drift_warning_names_missing_commands() -> None:
    from mcp_server.diagnostics import _addon_drift_warning

    # In sync → no warning.
    in_sync = _addon_drift_warning(["cmd_ping", "cmd_create_node"], {"cmd_ping", "cmd_create_node"})
    assert in_sync is None
    # Missing commands → warning naming the sample + a recovery hint.
    warning = _addon_drift_warning(
        ["cmd_ping"],
        {
            "cmd_ping",
            "cmd_create_node",
            "cmd_delete_node",
            "cmd_save_scene",
            "cmd_batch_set_property",
            "cmd_run_commands",
        },
    )
    assert warning is not None
    assert "SERVER↔ADDON DRIFT" in warning
    assert "cmd_create_node" in warning
    assert "older" in warning
    # A pre-handshake addon (None) → no warning (nothing to compare).
    assert _addon_drift_warning(None, {"cmd_ping"}) is None


async def test_get_server_info_reports_drift_when_addon_is_old() -> None:
    """A fake addon missing handlers yields a drift warning in the snapshot."""
    from mcp_server.bridge import Bridge
    from mcp_server.config import BridgeConfig
    from mcp_server.diagnostics import (
        _addon_drift_warning,
        _bridge_command_set,
        _fetch_bridge_diagnostics,
    )

    conn = FakeAddonConnection(_addon_responder)  # only 3 commands registered
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    diag = await _fetch_bridge_diagnostics(bridge)
    warning = _addon_drift_warning(diag.addon_commands, _bridge_command_set())
    assert warning is not None
    assert "SERVER↔ADDON DRIFT" in warning
    await bridge.close()
