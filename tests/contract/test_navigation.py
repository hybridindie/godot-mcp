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
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
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
        case "cmd_get_navigation_region":
            if p["node_path"] == "EmptyRegion":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "node_path": p["node_path"],
                        "has_polygon": False,
                        "outline_count": 0,
                        "vertex_count": 0,
                        "polygon_count": 0,
                    },
                )
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "has_polygon": True,
                    "outline_count": 1,
                    "vertex_count": 4,
                    "polygon_count": 1,
                },
            )
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
    async with Client(server, mode="legacy") as client:
        assert "godot_navigation_setup_region" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "godot_navigation_setup_region",
        "godot_navigation_setup_agent",
        "godot_navigation_bake_mesh",
        "godot_navigation_set_layers",
        "godot_navigation_get_region",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in {
        "godot_navigation_setup_region",
        "godot_navigation_setup_agent",
        "godot_navigation_bake_mesh",
        "godot_navigation_set_layers",
    })
    assert tools["godot_navigation_get_region"].meta["safety_class"] == "read_only"


async def test_region_agent_and_bake() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        region = await client.call_tool(
            "godot_navigation_setup_region",
            {"parent_path": ".", "region_type": "NavigationRegion3D"},
        )
        agent = await client.call_tool(
            "godot_navigation_setup_agent",
            {"parent_path": ".", "properties": {"radius": 12.0}},
        )
        baked = await client.call_tool(
            "godot_navigation_bake_mesh", {"node_path": "NavigationRegion3D"}
        )
    assert region.structured_content["region_type"] == "NavigationRegion3D"
    assert region.structured_content["node_path"] == "./NavigationRegion3D"
    assert agent.structured_content["agent_type"] == "NavigationAgent2D"
    assert baked.structured_content["baked"] is True


async def test_set_navigation_layers_bitmask() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        layers = await client.call_tool(
            "godot_navigation_set_layers", {"node_path": "NavigationRegion2D", "layers": [1, 3]}
        )
    assert layers.structured_content["navigation_layers"] == 5


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        result = await client.call_tool(
            "godot_navigation_bake_mesh", {"node_path": "NavigationRegion3D", "dry_run": True}
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_bake_navigation_mesh" not in _commands(conn)


async def test_get_navigation_region_returns_baked_data() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        result = await client.call_tool(
            "godot_navigation_get_region", {"node_path": "NavigationRegion2D"}
        )
    info = result.structured_content
    assert info["node_path"] == "NavigationRegion2D"
    assert info["has_polygon"] is True
    assert info["outline_count"] == 1
    assert info["vertex_count"] == 4
    assert info["polygon_count"] == 1


async def test_get_navigation_region_reports_empty_when_no_polygon() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        result = await client.call_tool(
            "godot_navigation_get_region", {"node_path": "EmptyRegion"}
        )
    info = result.structured_content
    assert info["has_polygon"] is False
    assert info["outline_count"] == 0
    assert info["vertex_count"] == 0
    assert info["polygon_count"] == 0


async def test_get_navigation_region_is_read_only() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "navigation"})
        await client.call_tool(
            "godot_navigation_get_region", {"node_path": "NavigationRegion2D"}
        )
    sent = _commands(conn)
    assert "cmd_get_navigation_region" in sent
    # read-only tool must not issue any mutation command
    assert not any(c.startswith("cmd_set_") or c == "cmd_bake_navigation_mesh" for c in sent)
