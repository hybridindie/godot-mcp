"""Contract tests for navigation tools (issue #43)."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_node_properties":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node"})
        case "cmd_setup_navigation_region":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "region_type": p["region_type"],
                    "created": True,
                },
            )
        case "cmd_setup_navigation_agent":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": f"{p['parent_path']}/{p['name']}",
                    "agent_type": p["agent_type"],
                    "created": True,
                },
            )
        case "cmd_bake_navigation_mesh":
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "baked": True})
        case "cmd_set_navigation_layers":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "navigation_layers": 5}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_navigation_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "setup_navigation_region" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "navigation"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "setup_navigation_region",
        "setup_navigation_agent",
        "bake_navigation_mesh",
        "set_navigation_layers",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_region_agent_and_bake() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "navigation"})
        region = await client.call_tool(
            "setup_navigation_region",
            {"parent_path": ".", "region_type": "NavigationRegion3D"},
        )
        agent = await client.call_tool(
            "setup_navigation_agent",
            {"parent_path": ".", "properties": {"radius": 12.0}},
        )
        baked = await client.call_tool("bake_navigation_mesh", {"node_path": "NavigationRegion3D"})
    assert region.structured_content["region_type"] == "NavigationRegion3D"
    assert region.structured_content["node_path"] == "./NavigationRegion3D"
    assert agent.structured_content["agent_type"] == "NavigationAgent2D"
    assert baked.structured_content["baked"] is True


async def test_set_navigation_layers_bitmask() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "navigation"})
        layers = await client.call_tool(
            "set_navigation_layers", {"node_path": "NavigationRegion2D", "layers": [1, 3]}
        )
    assert layers.structured_content["navigation_layers"] == 5


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "navigation"})
        result = await client.call_tool(
            "bake_navigation_mesh", {"node_path": "NavigationRegion3D", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_bake_navigation_mesh" not in _commands(conn)
