"""Contract tests for debug_workflow and debug_scene prompt."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client

from mcp_server.server import create_server


@pytest.fixture
def server() -> Any:
    return create_server()


async def _call_tool(server: Any, name: str, arguments: dict[str, str] | None = None) -> str:
    result = await server.call_tool(name, arguments=arguments or {})
    parts: list[str] = []
    for item in result.content:
        parts.append(str(getattr(item, "text", "")))
    return " ".join(parts)


async def _render_prompt(server: Any, name: str, arguments: dict[str, str] | None = None) -> Any:
    return await server.render_prompt(name, arguments=arguments)


async def _call_tool_via_client(
    server: Any, name: str, arguments: dict[str, str] | None = None
) -> str:
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool(name, arguments=arguments or {})
    parts: list[str] = []
    for item in result.content:
        parts.append(str(getattr(item, "text", "")))
    return " ".join(parts)


def test_debug_workflow_tool_exists(server: Any) -> None:
    """debug_workflow is registered and callable."""
    result_text = asyncio.run(_call_tool_via_client(server, "godot_debug_workflow"))
    assert "findings" in result_text
    assert "suggestions" in result_text


def test_debug_workflow_reports_bridge_state(server: Any) -> None:
    """The debug report always includes bridge connectivity."""
    result_text = asyncio.run(_call_tool_via_client(server, "godot_debug_workflow"))
    assert "bridge" in result_text


def test_debug_scene_prompt_registered(server: Any) -> None:
    """The debug_scene prompt appears in the prompt list."""
    prompts = asyncio.run(server.list_prompts())
    names = {p.name for p in prompts}
    assert "debug_scene" in names


def test_debug_scene_prompt_content(server: Any) -> None:
    """The debug_scene prompt mentions all debugging phases."""
    result = asyncio.run(_render_prompt(server, "debug_scene"))
    content = " ".join(str(m.content) for m in result.messages)
    assert "godot_debug_workflow" in content
    assert "godot_scripts_get_parse_errors" in content
    assert "godot_inspection_get_scene_tree" in content
    assert "godot_analysis_analyze_signal_flow" in content
    assert "godot_runtime_run_and_capture" in content
    assert "godot_runtime_play_scene" in content
    assert "godot_runtime_monitor_property" in content
    assert "godot_analysis_detect_circular_dependencies" in content
    assert "godot_analysis_find_unused_resources" in content


def test_debug_scene_prompt_parameterized(server: Any) -> None:
    """The debug_scene prompt accepts scene_path and script_path."""
    result = asyncio.run(
        _render_prompt(
            server,
            "debug_scene",
            {
                "scene_path": "res://level.tscn",
                "script_path": "res://scripts/hero.gd",
            },
        )
    )
    content = " ".join(str(m.content) for m in result.messages)
    assert "res://level.tscn" in content
    assert "res://scripts/hero.gd" in content
