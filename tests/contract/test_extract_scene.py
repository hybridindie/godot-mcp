"""Contract tests for extract-subtree-to-PackedScene (issue #531).

Drive the real FastMCP server over the in-memory client with a fake addon peer:
the tool routes to cmd_extract_scene with its params, returns a typed envelope
(persistence verdict included), honors dry_run with a node-list preview, and
surfaces the addon's structured refusals (non-owned/instanced subtrees).
"""

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
        case "cmd_node_exists":
            if p.get("node_path") == "Missing":
                return ResponseEnvelope.failure(
                    cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Missing'."
                )
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(
                cmd.id, {"is_open": True, "path": "res://main.tscn", "name": "main.tscn"}
            )
        case "cmd_node_persistence":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p.get("node_path", ""), "persisted": True}
            )
        case "cmd_extract_scene":
            if p.get("preview"):
                # The dry-run preview: node list + the same refusals as the real run.
                if p.get("node_path") == "Enemy/Part":
                    return ResponseEnvelope.failure(
                        cmd.id,
                        "VALIDATION_ERROR",
                        "Node 'Part' comes from the instanced scene 'res://enemy.tscn' (Editable "
                        "Children is off) — extracting it would silently drop those nodes on save. "
                        "Open 'res://enemy.tscn' and extract there, or enable Editable Children.",
                        "node_path",
                    )
                if p.get("node_path") == "Unowned":
                    return ResponseEnvelope.failure(
                        cmd.id,
                        "VALIDATION_ERROR",
                        "Node 'Unowned' has no owner in the edited scene (e.g. it was added by a "
                        "@tool script), so it is not saved — extracting it would produce a "
                        "prefab of a node that vanishes on reload. Save it first (set its "
                        "owner), then extract.",
                        "node_path",
                    )
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "node_path": p["node_path"],
                        "scene_path": p["scene_path"],
                        "extracted": False,
                        "replaced": False,
                        "saved": False,
                        "node_count": 3,
                        "persisted": True,
                    },
                )
            if p.get("node_path") == "Enemy/Part" or p.get("node_path") == "Unowned":
                return ResponseEnvelope.failure(
                    cmd.id,
                    "VALIDATION_ERROR",
                    "Node comes from the instanced scene 'res://enemy.tscn' (Editable Children "
                    "is off) — extracting it would silently drop those nodes on save.",
                    "node_path",
                )
            if p.get("scene_path") == "res://exists.tscn":
                return ResponseEnvelope.failure(
                    cmd.id, "VALIDATION_ERROR", "A scene already exists at 'res://exists.tscn'.",
                    "scene_path",
                )
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "scene_path": p["scene_path"],
                    "extracted": True,
                    "instance_path": "Player" if p["replace_with_instance"] else "",
                    "replaced": p["replace_with_instance"],
                    "saved": p["save_current"],
                    "node_count": 3,
                    # The real handler stamps the persistence verdict (with_persistence).
                    "persisted": True,
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_mutating_in_scene_edit() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_scene_edit_extract_scene" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        tools = {t.name: t for t in await client.list_tools()}
    tool = tools["godot_scene_edit_extract_scene"]
    assert tool.meta["safety_class"] == "mutating"
    annotations = tool.annotations
    assert annotations is not None and annotations.read_only_hint is False


async def test_extract_routes_params_and_returns_result() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {
                "node_path": "Player/Gun",
                "scene_path": "res://gun.tscn",
                "replace_with_instance": True,
                "save_current": True,
            },
        )
    sc = result.structured_content
    assert sc["scene_path"] == "res://gun.tscn"
    assert sc["extracted"] is True
    assert sc["replaced"] is True
    assert sc["saved"] is True
    assert sc["node_count"] == 3
    assert sc["persisted"] is True
    params = conn.last_command().params
    assert params["node_path"] == "Player/Gun"
    assert params["scene_path"] == "res://gun.tscn"
    assert params["replace_with_instance"] is True
    assert params["save_current"] is True


async def test_extract_defaults() -> None:
    # Defaults: no replacement, no save_current; dry_run=False.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Player/Gun", "scene_path": "res://gun.tscn"},
        )
    params = conn.last_command().params
    assert params["replace_with_instance"] is False
    assert params["save_current"] is False


async def test_extract_dry_run_lists_nodes() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {
                "node_path": "Player/Gun",
                "scene_path": "res://gun.tscn",
                "dry_run": True,
            },
        )
    sc = result.structured_content
    assert sc["dry_run"] is True
    assert sc["extracted"] is False
    # The preview carries the node list the real run would extract.
    assert sc["node_count"] == 3
    assert sc["persisted"] is True
    # The preview reached the addon (with preview=True); the real run did not.
    sent = [CommandEnvelope.model_validate_json(m).params.get("preview", False) for m in conn.sent]
    assert True in sent and conn.last_command().command == "cmd_extract_scene"


async def test_extract_refuses_instanced_subtree() -> None:
    # #477 family: extracting inside a non-editable instanced child would be
    # dropped on save — structured refusal with a hint, not silent partial work.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Enemy/Part", "scene_path": "res://part.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "Editable Children" in str(result.content)


async def test_extract_refuses_unowned_subtree() -> None:
    # A null owner on a non-root node (a @tool-script artifact) is never saved —
    # extraction would pack a phantom. Structured refusal, per the PR #556 review.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Unowned", "scene_path": "res://ghost.tscn", "dry_run": True},
            raise_on_error=False,
        )
    assert result.is_error
    assert "no owner" in str(result.content)


async def test_extract_existing_destination_is_structured_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Player", "scene_path": "res://exists.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "already exists" in str(result.content)


async def test_extract_dry_run_refuses_instanced_subtree() -> None:
    # A dry-run must refuse for the same reason the real run would — a preview
    # that would succeed and then fail for real is a lie.
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Enemy/Part", "scene_path": "res://part.tscn", "dry_run": True},
            raise_on_error=False,
        )
    assert result.is_error
    assert "Editable Children" in str(result.content)


async def test_extract_missing_node_is_precondition_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_extract_scene",
            {"node_path": "Missing", "scene_path": "res://gun.tscn"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)