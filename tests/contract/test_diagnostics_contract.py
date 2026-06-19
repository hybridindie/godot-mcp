"""Contract tests for the get_server_info diagnostics tool.

Verifies the diagnostics surface returns a comprehensive snapshot
including toolset counts, prompts, resources, bridge state, active scene,
and the troubleshooting cheat-sheet.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import FastMCP

from mcp_server.server import create_server


@pytest.fixture
def server() -> FastMCP:
    """A fully-built server with all tools, resources, and prompts."""
    return create_server()


async def _call_tool(server: FastMCP, name: str, arguments: dict[str, object] | None = None) -> str:
    """Async helper: call a tool and return its text content as a string."""
    result = await server.call_tool(name, arguments=arguments or {})
    # result.content is a list of TextContent; extract text from each.
    parts = []
    for item in result.content:
        parts.append(str(getattr(item, "text", "")))
    return " ".join(parts)


def test_diagnostics_tool_exists(server: FastMCP) -> None:
    """get_server_info is registered and callable."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    assert "godot-mcp" in result_text
    assert "toolsets" in result_text


def test_diagnostics_contains_toolset_summaries(server: FastMCP) -> None:
    """The response enumerates toolsets with counts."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    # Core + inspection are always present.
    assert "core" in result_text
    assert "inspection" in result_text
    assert "scene_edit" in result_text


def test_diagnostics_contains_prompts_list(server: FastMCP) -> None:
    """The response lists available prompts — empty list when no prompts registered."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    # Prompts are empty until #99; just verify the field exists.
    assert '"prompts"' in result_text


def test_diagnostics_contains_resources_list(server: FastMCP) -> None:
    """The response lists available resource URIs."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    assert "godot://project/info" in result_text
    assert "godot://scene/current" in result_text


def test_diagnostics_contains_common_errors(server: FastMCP) -> None:
    """The response includes the troubleshooting cheat-sheet."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    assert "BRIDGE_DISCONNECTED" in result_text
    assert "PRECONDITION_FAILED" in result_text
    assert "ToolError: unknown tool" in result_text


def test_diagnostics_contains_next_steps(server: FastMCP) -> None:
    """The response suggests next actions based on bridge/scene state."""
    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    assert "next_steps" in result_text


def test_diagnostics_exposes_contract_version(server: FastMCP) -> None:
    """The response carries a machine-readable contract/compat surface (#196).

    A monotonic integer contract version distinct from the CalVer build version,
    plus the oldest client contract the server still serves, so clients can
    negotiate against contract drift rather than guessing from CalVer.
    """
    import json

    from mcp_server import CONTRACT_VERSION, MIN_COMPATIBLE_CONTRACT

    result_text = asyncio.run(_call_tool(server, "get_server_info"))
    payload = json.loads(result_text)

    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["min_compatible_contract"] == MIN_COMPATIBLE_CONTRACT
    # Negotiation range is well-formed and distinct from the CalVer build version.
    assert isinstance(payload["contract_version"], int)
    assert payload["min_compatible_contract"] <= payload["contract_version"]
    assert payload["contract_version"] >= 1
