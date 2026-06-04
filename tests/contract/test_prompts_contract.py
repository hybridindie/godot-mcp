"""Contract tests for MCP prompts (issue #12).

Prompts are instruction templates — they do not act, they return messages.
We verify they are registered on the server, their names are discoverable,
and they return the expected structured content.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_server.server import create_server


@pytest.fixture
def server():
    """A fully-built server with all tools, resources, and prompts."""
    return create_server()


async def _get_prompt_names(server) -> set[str]:
    """Async helper: list all registered prompt names."""
    prompts = await server.list_prompts()
    return {p.name for p in prompts}


async def _render_prompt(server, name: str, arguments: dict | None = None):
    """Async helper: render a prompt with optional arguments."""
    return await server.render_prompt(name, arguments=arguments)


def test_prompts_are_registered(server) -> None:
    """Every expected prompt name appears in the server's prompt list."""
    expected = {
        "toolset_discovery",
        "build_scene",
        "play_test",
        "script_edit",
        "troubleshoot",
    }
    names = asyncio.run(_get_prompt_names(server))
    assert expected <= names, f"Missing prompts: {expected - names}"


def test_toolset_discovery_prompt_returns_messages(server) -> None:
    """The toolset_discovery prompt returns a non-empty list of messages."""
    result = asyncio.run(_render_prompt(server, "toolset_discovery"))
    assert result is not None
    assert len(result.messages) > 0
    # The message content should mention list_toolsets and enable_toolset.
    content = " ".join(str(m.content) for m in result.messages)
    assert "list_toolsets" in content
    assert "enable_toolset" in content


def test_build_scene_prompt_parameterized(server) -> None:
    """The build_scene prompt accepts scene_path and root_type arguments."""
    result = asyncio.run(_render_prompt(server, "build_scene", {"scene_path": "res://level.tscn", "root_type": "Node3D"}))
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://level.tscn" in content
    assert "Node3D" in content


def test_play_test_prompt_parameterized(server) -> None:
    """The play_test prompt accepts a scene_path argument."""
    result = asyncio.run(_render_prompt(server, "play_test", {"scene_path": "res://demo.tscn"}))
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://demo.tscn" in content
    assert "play_scene" in content
    assert "get_game_scene_tree" in content


def test_script_edit_prompt_parameterized(server) -> None:
    """The script_edit prompt accepts script_path and node_path arguments."""
    result = asyncio.run(_render_prompt(server, "script_edit", {"script_path": "res://scripts/hero.gd", "node_path": "./Hero"}))
    assert result is not None
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://scripts/hero.gd" in content
    assert "./Hero" in content
    assert "write_script" in content
    assert "patch_script" in content


def test_troubleshoot_prompt_returns_messages(server) -> None:
    """The troubleshoot prompt returns a diagnostic checklist."""
    result = asyncio.run(_render_prompt(server, "troubleshoot"))
    assert result is not None
    assert len(result.messages) > 0
    content = " ".join(str(m.content) for m in result.messages)
    assert "get_server_info" in content
    assert "bridge is disconnected" in content
    assert "PRECONDITION_FAILED" in content
    assert "DOCUMENTATION" in content
