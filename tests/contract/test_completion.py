"""Contract tests for argument completion (``@mcp.completion``) — issue #314.

A registered completion handler advertises the completions capability and
answers ``completion/complete`` requests for path-bearing prompt arguments
(scene_path, node_path, resource_path, script_path). These tests drive the
real server through a FastMCP Client against a fake addon bridge so the
envelope shapes and bridge routing are exercised end-to-end.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from mcp_types import PromptReference

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_list_scenes":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "scenes": [
                        {"path": "res://scenes/main.tscn", "is_main": True},
                        {"path": "res://scenes/level1.tscn"},
                        {"path": "res://scenes/level2.tscn"},
                        {"path": "res://ui/menu.tscn"},
                    ],
                    "main_scene": "res://scenes/main.tscn",
                },
            )
        case "cmd_get_scene_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "tree": {
                        "name": "Main",
                        "type": "Node2D",
                        "path": ".",
                        "children": [
                            {
                                "name": "Player",
                                "type": "CharacterBody2D",
                                "path": "Player",
                                "children": [
                                    {
                                        "name": "Sprite",
                                        "type": "Sprite2D",
                                        "path": "Player/Sprite",
                                        "children": [],
                                    }
                                ],
                            },
                            {
                                "name": "Camera",
                                "type": "Camera2D",
                                "path": "Camera",
                                "children": [],
                            },
                        ],
                    }
                },
            )
        case "cmd_list_scripts":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "directory": "res://",
                    "scripts": [
                        "res://scripts/hero.gd",
                        "res://scripts/enemy.gd",
                        "res://scripts/ui/hud.gd",
                    ],
                    "total": 3,
                    "returned": 3,
                },
            )
        case "cmd_search_files":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "matches": [
                        "res://resources/player.tres",
                        "res://resources/enemy.tres",
                        "res://ui/theme.tres",
                    ],
                    "truncated": False,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_completions_capability_advertised() -> None:
    """Registering @mcp.completion declares the server's completions handler."""
    server, _ = _build()
    # The handler is registered on the FastMCP server, advertising the
    # completions capability at negotiation (FastMCP wires this on register).
    assert server._completion_handler is not None


async def test_complete_scene_path_filters_by_partial() -> None:
    """scene_path completion returns scene paths starting with the partial value."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="build_scene"),
            argument={"name": "scene_path", "value": "res://scenes/"},
        )
    paths = set(completion.values)
    assert "res://scenes/main.tscn" in paths
    assert "res://scenes/level1.tscn" in paths
    assert "res://scenes/level2.tscn" in paths
    # The partial excludes scenes outside res://scenes/.
    assert "res://ui/menu.tscn" not in paths


async def test_complete_scene_path_empty_returns_all_scenes() -> None:
    """An empty partial returns every scene the addon reports."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="build_scene"),
            argument={"name": "scene_path", "value": ""},
        )
    assert set(completion.values) == {
        "res://scenes/main.tscn",
        "res://scenes/level1.tscn",
        "res://scenes/level2.tscn",
        "res://ui/menu.tscn",
    }


async def test_complete_node_path_filters_by_partial() -> None:
    """node_path completion returns scene-tree paths starting with the partial."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="script_edit"),
            argument={"name": "node_path", "value": "Player"},
        )
    paths = set(completion.values)
    assert "Player" in paths
    assert "Player/Sprite" in paths
    assert "Camera" not in paths


async def test_complete_script_path_filters_by_partial() -> None:
    """script_path completion returns .gd paths starting with the partial."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="script_edit"),
            argument={"name": "script_path", "value": "res://scripts/"},
        )
    paths = set(completion.values)
    assert "res://scripts/hero.gd" in paths
    assert "res://scripts/enemy.gd" in paths
    assert "res://scripts/ui/hud.gd" in paths
    assert "res://resources/player.tres" not in paths


async def test_complete_resource_path_filters_by_partial() -> None:
    """resource_path / save_path completion returns .tres resource paths."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="author_resource"),
            argument={"name": "save_path", "value": "res://resources/"},
        )
    paths = set(completion.values)
    assert "res://resources/player.tres" in paths
    assert "res://resources/enemy.tres" in paths
    assert "res://ui/theme.tres" not in paths


async def test_complete_unknown_argument_returns_empty() -> None:
    """An argument we don't handle yields no candidates (not an error)."""
    server, _ = _build()
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="build_scene"),
            argument={"name": "root_type", "value": "Node"},
        )
    assert completion.values == []


async def test_complete_when_bridge_disconnected_returns_empty() -> None:
    """With no editor connected, completion returns no candidates (no crash)."""
    from tests.fakes import null_serve

    bridge = Bridge(ServerConfig().bridge, serve=null_serve)
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        completion = await client.complete(
            ref=PromptReference(name="build_scene"),
            argument={"name": "scene_path", "value": ""},
        )
    assert completion.values == []