"""Contract tests for animation tools (issue #39)."""

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
        case "cmd_create_animation":
            return ResponseEnvelope.success(
                cmd.id,
                {"player_path": p["node_path"], "animation": p["name"], "length": p["length"]},
            )
        case "cmd_add_animation_track":
            return ResponseEnvelope.success(
                cmd.id, {"animation": p["animation"], "track": 0, "track_path": p["track_path"]}
            )
        case "cmd_insert_keyframe":
            return ResponseEnvelope.success(
                cmd.id, {"animation": p["animation"], "track": p["track"], "time": p["time"]}
            )
        case "cmd_create_animation_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {"node_path": f"{p['parent_path']}/{p['name']}", "root_type": p["root_type"]},
            )
        case "cmd_add_state_machine_state":
            return ResponseEnvelope.success(
                cmd.id, {"tree_path": p["tree_path"], "state": p["state_name"]}
            )
        case "cmd_set_blend_tree_node":
            return ResponseEnvelope.success(
                cmd.id,
                {"tree_path": p["tree_path"], "node": p["node_name"], "node_type": p["node_type"]},
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_gated_in_animation_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "create_animation" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "animation"})
        tools = {t.name: t for t in await client.list_tools()}
    expected = {
        "create_animation",
        "add_animation_track",
        "insert_keyframe",
        "create_animation_tree",
        "add_state_machine_state",
        "set_blend_tree_node",
    }
    assert expected <= set(tools)
    assert all(tools[n].meta["safety_class"] == "mutating" for n in expected)


async def test_create_animation_and_track_and_keyframe() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "animation"})
        anim = await client.call_tool(
            "create_animation", {"node_path": "AnimationPlayer", "name": "walk", "length": 2.0}
        )
        track = await client.call_tool(
            "add_animation_track",
            {
                "node_path": "AnimationPlayer",
                "animation": "walk",
                "track_path": "Sprite2D:position",
            },
        )
        key = await client.call_tool(
            "insert_keyframe",
            {
                "node_path": "AnimationPlayer",
                "animation": "walk",
                "track": 0,
                "time": 0.5,
                "value": "Vector2(10, 20)",
            },
        )
    assert anim.structured_content["animation"] == "walk"
    assert anim.structured_content["length"] == 2.0
    assert track.structured_content["track"] == 0
    assert key.structured_content["time"] == 0.5


async def test_animation_tree_state_machine_and_blend_tree() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "animation"})
        tree = await client.call_tool(
            "create_animation_tree", {"parent_path": ".", "name": "AnimationTree"}
        )
        state = await client.call_tool(
            "add_state_machine_state", {"tree_path": "./AnimationTree", "state_name": "idle"}
        )
        blend = await client.call_tool(
            "set_blend_tree_node",
            {
                "tree_path": "./AnimationTree",
                "node_name": "anim",
                "node_type": "AnimationNodeAnimation",
            },
        )
    assert tree.structured_content["node_path"] == "./AnimationTree"
    assert state.structured_content["state"] == "idle"
    assert blend.structured_content["node_type"] == "AnimationNodeAnimation"


async def test_create_tree_dry_run_previews_path() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "animation"})
        result = await client.call_tool(
            "create_animation_tree", {"parent_path": "World", "name": "SM", "dry_run": True}
        )
    # dry_run previews the scene-relative path (parent + name), not an empty string.
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["node_path"] == "World/SM"
    assert "cmd_create_animation_tree" not in _commands(conn)


async def test_dry_run_sends_no_mutation() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "animation"})
        result = await client.call_tool(
            "create_animation",
            {"node_path": "AnimationPlayer", "name": "walk", "dry_run": True},
        )
    assert result.structured_content["dry_run"] is True
    assert "cmd_create_animation" not in _commands(conn)
