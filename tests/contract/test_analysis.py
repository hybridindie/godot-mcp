"""Contract tests for static analysis tools (issue #49).

These read project files from disk; the project dir is set via config (no editor needed),
so the tools run end-to-end against a synthetic temp project with a fake bridge.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _make_project(root: Path) -> None:
    (root / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (root / "main.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Texture2D" path="res://used.png" id="1"]\n'
        '[node name="Main" type="Node2D"]\n'
        '[node name="Button" type="Button" parent="."]\n'
        '[connection signal="pressed" from="Button" to="." method="_go"]\n',
        encoding="utf-8",
    )
    (root / "used.png").write_bytes(b"\x89PNG")
    (root / "unused.png").write_bytes(b"\x89PNG")


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "bridge unused for analysis")


def _server(project_dir: Path) -> FastMCP:
    config = ServerConfig(bridge=BridgeConfig(), godot_project_dir=str(project_dir))
    bridge = Bridge(
        config.bridge, connector=connector_for(FakeAddonConnection(responder=_responder))
    )
    return create_server(config, bridge=bridge)


async def test_gated_read_only_in_analysis_toolset(tmp_path: Path) -> None:
    _make_project(tmp_path)
    async with Client(_server(tmp_path)) as client:
        assert "project_stats" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "analysis"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "find_unused_resources",
        "analyze_signal_flow",
        "detect_circular_dependencies",
        "project_stats",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "read_only" for n in expected)


async def test_find_unused_and_signal_flow(tmp_path: Path) -> None:
    _make_project(tmp_path)
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        unused = await client.call_tool("find_unused_resources", {})
        flow = await client.call_tool("analyze_signal_flow", {})
    assert "res://unused.png" in unused.structured_content["unused"]
    assert "res://used.png" not in unused.structured_content["unused"]
    conn = flow.structured_content["connections"][0]
    assert conn["signal"] == "pressed"
    assert conn["from"] == "Button" and conn["to"] == "."  # serialized by alias


async def test_project_stats(tmp_path: Path) -> None:
    _make_project(tmp_path)
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        stats = await client.call_tool("project_stats", {})
    sc = stats.structured_content
    assert sc["scenes"] == 1 and sc["total_nodes"] == 2 and sc["connections"] == 1


async def test_missing_project_dir_is_precondition_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    async with Client(_server(missing)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        result = await client.call_tool("project_stats", {}, raise_on_error=False)
    assert result.is_error
    assert "project_dir" in str(result.content)
