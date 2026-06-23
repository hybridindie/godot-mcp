"""Contract tests for testing / QA tools (issue #37)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.qa import encode_png
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_play_scene":
            return ResponseEnvelope.success(cmd.id, {"playing": True, "scene": p["scene_path"]})
        case "cmd_stop_scene":
            return ResponseEnvelope.success(cmd.id, {"playing": False})
        case "cmd_is_playing":
            return ResponseEnvelope.success(cmd.id, {"playing": True, "scene": "x"})
        case "cmd_get_game_scene_tree":
            return ResponseEnvelope.success(
                cmd.id, {"playing": True, "connected": True, "tree": {}}
            )
        case "cmd_play_input_sequence":
            return ResponseEnvelope.success(
                cmd.id, {"sent": True, "kind": "sequence", "count": len(p["events"])}
            )
        case "cmd_monitor_property":
            return ResponseEnvelope.success(
                cmd.id, {"monitoring": True, "node_path": p["node_path"], "property": p["property"]}
            )
        case "cmd_get_property_samples":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "connected": True,
                    "samples": [{"frame": 1, "value": 100}],
                    "error": "",
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _solid(w: int, h: int, rgba: tuple[int, int, int, int]) -> str:
    return encode_png(w, h, [list(rgba) * w for _ in range(h)])


async def test_gated_with_safety_classes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "godot_testing_run_test_scenario" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_testing_assert_node_state",
        "godot_testing_run_test_scenario",
        "godot_testing_run_stress_test",
        "godot_testing_compare_screenshots",
    }
    assert expected <= set(tools)
    assert tools["godot_testing_run_test_scenario"].meta["safety_class"] == "runtime"
    assert tools["godot_testing_run_stress_test"].meta["safety_class"] == "runtime"
    assert tools["godot_testing_assert_node_state"].meta["safety_class"] == "read_only"
    assert tools["godot_testing_compare_screenshots"].meta["safety_class"] == "read_only"


async def test_assert_node_state_passes_and_fails() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        ok = await client.call_tool(
            "godot_testing_assert_node_state",
            {"node_path": "Player", "property": "health", "expected": 100},
        )
        bad = await client.call_tool(
            "godot_testing_assert_node_state",
            {"node_path": "Player", "property": "health", "expected": 50, "op": "<"},
        )
    assert ok.structured_content["passed"] is True and ok.structured_content["actual"] == 100
    assert bad.structured_content["passed"] is False  # 100 < 50 is false


async def test_run_test_scenario_evaluates_assertions() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        result = await client.call_tool(
            "godot_testing_run_test_scenario",
            {
                "scene": "res://main.tscn",
                "events": [{"type": "key", "key": "Space"}],
                "assertions": [
                    {"node_path": "Player", "property": "health", "expected": 100, "op": "=="}
                ],
                "setup_ms": 400,
                "settle_ms": 50,
            },
        )
    sc = result.structured_content
    assert sc["played"] is True and sc["connected"] is True
    assert sc["passed"] is True and sc["assertions"][0]["passed"] is True


async def test_run_stress_test_reports_survival() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        result = await client.call_tool(
            "godot_testing_run_stress_test", {"iterations": 10, "seed": 3}
        )
    assert result.structured_content["survived"] is True
    assert result.structured_content["iterations"] == 10


async def test_compare_screenshots_match_and_diff() -> None:
    server, _ = _build()
    black = _solid(3, 3, (0, 0, 0, 255))
    white = _solid(3, 3, (255, 255, 255, 255))
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        same = await client.call_tool(
            "godot_testing_compare_screenshots", {"image_a": black, "image_b": black}
        )
        diff = await client.call_tool(
            "godot_testing_compare_screenshots", {"image_a": black, "image_b": white}
        )
    assert same.structured_content["match"] is True
    assert (
        diff.structured_content["match"] is False and diff.structured_content["diff_ratio"] == 1.0
    )
