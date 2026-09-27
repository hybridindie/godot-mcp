"""Contract tests: dedicated one-shot property read (issue #571).

The runtime probe has a single monitor slot. ``assert_node_state`` implemented
its live read as ``cmd_monitor_property`` with ``samples: 1`` — calling it mid
capture replaced the running capture, and ``get_property_samples`` then returned
the one-shot's series (a different node/property, 1 sample) as ``ready: true``.
The requested series was lost without any error.

Contract:
- A dedicated ``cmd_read_property`` one-shot read exists (tool
  ``godot_runtime_read_property``): reads the live value NOW via the probe's
  ``read_property`` message and never touches the monitor slot.
- ``assert_node_state`` (and scenario assertions) read through
  ``cmd_read_property`` — no ``cmd_monitor_property`` with ``samples: 1`` is
  ever sent, so a mid-capture assert cannot clobber the monitor.
- The monitor surface is unchanged: ``monitor_property`` +
  ``get_property_samples`` keep their envelope shapes.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = [pytest.mark.filterwarnings("ignore::pytest.PytestWarning"), pytest.mark.asyncio]


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [
        CommandEnvelope.model_validate_json(m).command for m in conn.sent
    ]

READ_REPLY = {
    "ready": True,
    "node_path": "/root/Scene/Body",
    "property": "global_position",
    "value": {"x": 1.0, "y": 2.0, "z": 3.0},
    "error": "",
}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_read_property":
            return ResponseEnvelope.success(cmd.id, {**READ_REPLY, "ready": True})
        case "cmd_monitor_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "monitoring": True,
                    "node_path": cmd.params["node_path"],
                    "property": cmd.params["property"],
                },
            )
        case "cmd_get_property_samples":
            return ResponseEnvelope.success(
                cmd.id,
                {"ready": True, "connected": True, "samples": [{"frame": 1, "value": 1}]},
            )
        case "cmd_play_scene" | "cmd_play_input_sequence" | "cmd_stop_scene":
            return ResponseEnvelope.success(cmd.id, {"playing": True, "sent": True})
        case "cmd_get_game_scene_tree":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "connected": True, "tree": {}}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_read_property_tool_exists_and_is_read_only() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    assert "godot_runtime_read_property" in tools
    assert tools["godot_runtime_read_property"].meta["safety_class"] == "read_only"


async def test_read_property_returns_live_value() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_read_property",
            {"node_path": "/root/Scene/Body", "property": "global_position"},
        )
    sc = result.structured_content
    assert sc["ready"] is True
    assert sc["value"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert sc["property"] == "global_position"


async def test_read_property_forwards_node_and_property() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool(
            "godot_runtime_read_property",
            {"node_path": "/root/Scene/Body", "property": "global_position"},
        )
    assert conn.last_command().command == "cmd_read_property"
    params = conn.last_command().params
    assert params["node_path"] == "/root/Scene/Body"
    assert params["property"] == "global_position"


async def test_assert_node_state_reads_via_read_property_not_monitor() -> None:
    """#571 core: an assert must NEVER send cmd_monitor_property with samples:1 —
    that is what silently replaced a running capture."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        result = await client.call_tool(
            "godot_testing_assert_node_state",
            {
                "node_path": "/root/Scene/Body",
                "property": "global_position",
                "expected": {"x": 1.0, "y": 2.0, "z": 3.0},
            },
        )
    assert result.structured_content["passed"] is True
    commands = _commands(conn)
    assert "cmd_read_property" in commands, commands
    assert "cmd_monitor_property" not in commands, (
        f"#571 regression: assert went through the monitor slot: {commands}"
    )


async def test_scenario_assertions_use_read_property_too() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        await client.call_tool(
            "godot_testing_run_test_scenario",
            {
                "scene": "res://main.tscn",
                "assertions": [
                    {
                        "node_path": "/root/Body",
                        "property": "global_position",
                        "expected": {"x": 1.0, "y": 2.0, "z": 3.0},
                    }
                ],
                "setup_ms": 200,
                "settle_ms": 10,
            },
        )
    commands = _commands(conn)
    assert "cmd_read_property" in commands
    assert "cmd_monitor_property" not in commands


# --- addon wiring (GDScript can't run outside Godot: source-scan contract) ---


def test_probe_has_dedicated_read_property_message() -> None:
    from pathlib import Path

    probe = (
        Path(__file__).resolve().parents[2]
        / "godot"
        / "addons"
        / "godot_mcp"
        / "mcp_runtime_probe.gd"
    ).read_text()
    assert '"read_property":' in probe, "probe must route a read_property capture message"
    assert "func _read_property" in probe, "probe must implement the one-shot reader"
    assert "godot_mcp:read_property" in probe, "probe must reply on its own channel"
    # The one-shot reader shares no state with the monitor slot.
    reader = probe.split("func _read_property", 1)[1].split("func ", 1)[0]
    assert "_monitor_" not in reader, "the one-shot read must not touch monitor state"


def test_debugger_gates_read_property_replies_on_request_id() -> None:
    """Qodo review (#575): a delayed reply to an OLDER request must never serve
    as the current request's result — the debugger's capture gates on the
    pending request_id, and the handler re-verifies before returning."""
    from pathlib import Path

    addon = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
    capture = (addon / "mcp_debugger.gd").read_text().split(
        '"godot_mcp:read_property":', 1
    )[1].split("return true", 1)[0]
    assert "request_id" in capture and "_read_property_pending" in capture, (
        "godot_mcp:read_property capture must gate the cache on the pending request_id"
    )
    handler = (addon / "handlers" / "runtime_inspect.gd").read_text().split(
        "func _cmd_read_property", 1
    )[1].split("func ", 1)[0]
    # The handler re-verifies the id (belt-and-braces) instead of returning the
    # cache unconditionally.
    assert 'get("request_id") == request_id' in handler
    assert "read_pending" in handler


def test_one_shot_read_smoke_is_wired_into_pytest() -> None:
    from tests.integration.test_addon_read_smokes import SMOKES

    assert ("one_shot_read_smoke.gd", "ONE_SHOT_READ_TEST_OK") in SMOKES