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
        "project_structure",
        "analyze_dependencies",
        "find_orphaned_resources",
        "validate_scene_integrity",
        "cross_scene_find_refs",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "read_only" for n in expected)


async def test_project_structure_returns_inventory(tmp_path: Path) -> None:
    _make_project(tmp_path)
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        result = await client.call_tool("project_structure", {})
    data = result.structured_content
    assert "res://main.tscn" in data["scenes"]
    assert "res://unused.png" in data["resources"]
    assert "res://main.tscn" in data["entry_points"]


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


async def test_analyze_dependencies(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (tmp_path / "icon.png").write_bytes(b"\x89PNG")
    (tmp_path / "player.gd").write_text(
        'extends CharacterBody2D\nconst Explosion = preload("res://explosion.tscn")\n',
        encoding="utf-8",
    )
    (tmp_path / "main.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Script" path="res://player.gd" id="1"]\n'
        '[ext_resource type="Texture2D" path="res://icon.png" id="2"]\n'
        '[node name="Main" type="Node2D"]\n'
        '[node name="Player" type="CharacterBody2D" parent="."]\n'
        'script = ExtResource("1")\n',
        encoding="utf-8",
    )
    (tmp_path / "explosion.tscn").write_bytes(b"\x00")  # binary-ish stub
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        deps = await client.call_tool(
            "analyze_dependencies", {"resource_path": "res://player.gd"}
        )
    sc = deps.structured_content
    assert sc["path"] == "res://player.gd"
    assert "res://explosion.tscn" in sc["references"]


async def test_find_orphaned_resources(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (tmp_path / "used.png").write_bytes(b"\x89PNG")
    (tmp_path / "orphan.png").write_bytes(b"\x89PNG")
    (tmp_path / "main.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Texture2D" path="res://used.png" id="1"]\n'
        '[node name="Main" type="Node2D"]\n',
        encoding="utf-8",
    )
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        orphans = await client.call_tool("find_orphaned_resources", {})
    sc = orphans.structured_content
    assert any(o["path"] == "res://orphan.png" for o in sc["orphaned"])
    assert all(o["path"] != "res://used.png" for o in sc["orphaned"])
    assert sc["scanned"] >= 2


async def test_validate_scene_integrity(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (tmp_path / "main.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Script" path="res://missing.gd" id="1"]\n'
        '[node name="Main" type="Node2D"]\n'
        '[node name="Child" type="Sprite2D" parent="."]\n'
        'script = ExtResource("1")\n',
        encoding="utf-8",
    )
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        integrity = await client.call_tool(
            "validate_scene_integrity", {"scene_path": "res://main.tscn"}
        )
    sc = integrity.structured_content
    assert sc["valid"] is False
    assert any(
        e["severity"] == "error" and "missing.gd" in e["message"]
        for e in sc["errors"]
    )


async def test_cross_scene_find_refs(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        encoding="utf-8",
    )
    (tmp_path / "shared.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "a.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Script" path="res://shared.gd" id="1"]\n'
        '[node name="A" type="Node2D"]\n',
        encoding="utf-8",
    )
    (tmp_path / "b.tscn").write_text(
        "[gd_scene format=3]\n"
        '[ext_resource type="Script" path="res://shared.gd" id="1"]\n'
        '[node name="B" type="Node2D"]\n',
        encoding="utf-8",
    )
    async with Client(_server(tmp_path)) as client:
        await client.call_tool("enable_toolset", {"category": "analysis"})
        refs = await client.call_tool(
            "cross_scene_find_refs", {"target_path": "res://shared.gd"}
        )
    sc = refs.structured_content
    assert "res://a.tscn" in sc["scenes"]
    assert "res://b.tscn" in sc["scenes"]
    assert sc["scripts"] == []
    assert sc["resources"] == []
