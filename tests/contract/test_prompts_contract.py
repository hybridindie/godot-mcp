"""Contract tests for MCP prompts (issue #12).

Prompts are instruction templates — they do not act, they return messages.
We verify they are registered on the server, their names are discoverable,
and they return the expected structured content.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mcp_server.server import create_server


@pytest.fixture
def server() -> Any:
    """A fully-built server with all tools, resources, and prompts."""
    return create_server()


async def _get_prompt_names(server: Any) -> set[str]:
    """Async helper: list all registered prompt names."""
    prompts = await server.list_prompts()
    return {p.name for p in prompts}


async def _render_prompt(server: Any, name: str, arguments: dict[str, str] | None = None) -> Any:
    """Async helper: render a prompt with optional arguments."""
    return await server.render_prompt(name, arguments=arguments)


def test_prompts_are_registered(server: Any) -> None:
    """Every expected prompt name appears in the server's prompt list."""
    expected = {
        "toolset_discovery",
        "build_scene",
        "play_test",
        "script_edit",
        "troubleshoot",
        "author_resource",
        "export_build",
        "batch_refactor",
    }
    names = asyncio.run(_get_prompt_names(server))
    assert expected <= names, f"Missing prompts: {expected - names}"


def test_toolset_discovery_prompt_returns_messages(server: Any) -> None:
    """The toolset_discovery prompt returns a non-empty list of messages."""
    result = asyncio.run(_render_prompt(server, "toolset_discovery"))
    assert result is not None
    assert len(result.messages) > 0
    # The message content should mention list_toolsets and enable_toolset.
    content = " ".join(str(m.content) for m in result.messages)
    assert "godot_list_toolsets" in content
    assert "godot_enable_toolset" in content


def test_build_scene_prompt_parameterized(server: Any) -> None:
    """The build_scene prompt accepts scene_path and root_type arguments."""
    result = asyncio.run(
        _render_prompt(
            server,
            "build_scene",
            {"scene_path": "res://level.tscn", "root_type": "Node3D"},
        )
    )
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://level.tscn" in content
    assert "Node3D" in content


def test_play_test_prompt_parameterized(server: Any) -> None:
    """The play_test prompt accepts a scene_path argument."""
    result = asyncio.run(_render_prompt(server, "play_test", {"scene_path": "res://demo.tscn"}))
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://demo.tscn" in content
    assert "godot_runtime_play_scene" in content
    assert "godot_runtime_get_game_scene_tree" in content


def test_script_edit_prompt_parameterized(server: Any) -> None:
    """The script_edit prompt accepts script_path and node_path arguments."""
    result = asyncio.run(
        _render_prompt(
            server,
            "script_edit",
            {
                "script_path": "res://scripts/hero.gd",
                "node_path": "./Hero",
            },
        )
    )
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://scripts/hero.gd" in content
    assert "./Hero" in content
    assert "godot_scripts_write" in content
    assert "godot_scripts_patch" in content


def test_author_resource_prompt_parameterized(server: Any) -> None:
    """author_resource branches on resource_kind and cites the right toolset/tools."""
    tileset = asyncio.run(
        _render_prompt(
            server,
            "author_resource",
            {"resource_kind": "tileset", "save_path": "res://tiles/ground.tres"},
        )
    )
    content = " ".join(str(m.content) for m in tileset.messages)
    assert "res://tiles/ground.tres" in content
    assert "godot_enable_toolset('tilemap')" in content
    assert "godot_tilemap_create_tileset" in content
    assert "godot_tilemap_add_tileset_atlas_source" in content

    # A different kind routes to a different toolset.
    shader = asyncio.run(_render_prompt(server, "author_resource", {"resource_kind": "shader"}))
    shader_content = " ".join(str(m.content) for m in shader.messages)
    assert "godot_enable_toolset('shader')" in shader_content
    assert "godot_shader_create" in shader_content


def test_export_build_prompt_parameterized(server: Any) -> None:
    """export_build accepts preset/output_path and walks the export toolset."""
    result = asyncio.run(
        _render_prompt(
            server,
            "export_build",
            {"preset": "Windows Desktop", "output_path": "res://build/game.exe"},
        )
    )
    content = " ".join(str(m.content) for m in result.messages)
    assert "Windows Desktop" in content
    assert "res://build/game.exe" in content
    assert "godot_enable_toolset('export')" in content
    assert "godot_export_list_presets" in content
    assert "godot_export_project" in content


def test_batch_refactor_prompt_parameterized(server: Any) -> None:
    """batch_refactor previews with dry_run before applying across many nodes."""
    result = asyncio.run(
        _render_prompt(
            server,
            "batch_refactor",
            {"node_type": "Sprite2D", "property": "modulate", "value": "#ff0000"},
        )
    )
    content = " ".join(str(m.content) for m in result.messages)
    assert "Sprite2D" in content
    assert "modulate" in content
    assert "godot_enable_toolset('batch')" in content
    assert "godot_batch_find_nodes_by_type" in content
    assert "godot_batch_set_property" in content
    assert "dry_run=True" in content


def test_troubleshoot_prompt_returns_messages(server: Any) -> None:
    """The troubleshoot prompt returns a diagnostic checklist."""
    result = asyncio.run(_render_prompt(server, "troubleshoot"))
    assert result is not None
    assert len(result.messages) > 0
    content = " ".join(str(m.content) for m in result.messages)
    assert "godot_get_server_info" in content
    assert "bridge is disconnected" in content
    assert "PRECONDITION_FAILED" in content
    assert "DOCUMENTATION" in content
