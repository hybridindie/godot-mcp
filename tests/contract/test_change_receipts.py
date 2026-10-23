"""Contract: mutating results carry a change receipt (issue #756).

The receipt is additive to the persistence verdict: it says what actually
changed (from the addon's read-back), including the honest ``noop`` when a write
did not land. The addon side emits it from the node handlers; this pins the
server model/parsing and the shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _server(responder: Any) -> FastMCP:
    config = ServerConfig()
    bridge = Bridge(
        config.bridge,
        connector=connector_for(FakeAddonConnection(responder)),
    )
    return create_server(config, bridge=bridge)


def _base(command: Any) -> ResponseEnvelope | None:
    return make_addon_responder(godot_version="4.7.2-stable")(command)


def _receipt(status: str, changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "changes": changes or [],
        "truncated": False,
    }


def _responder(command: Any) -> ResponseEnvelope | None:
    if command.command == "cmd_get_active_scene":
        return ResponseEnvelope.success(
            command.id, {"is_open": True, "path": "res://main.tscn", "name": "Main"}
        )
    if command.command == "cmd_node_exists":
        return ResponseEnvelope.success(command.id, {"exists": True})
    if command.command == "cmd_create_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": "Root/New",
                "created": True,
                "receipt": _receipt(
                    "created",
                    [
                        {
                            "path": "Root/New",
                            "op": "add",
                            "before": None,
                            "after": {"type": "Node2D", "name": "New"},
                        }
                    ],
                ),
            },
        )
    if command.command == "cmd_rename_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": "Root/Renamed",
                "old_name": "Old",
                "new_name": "Renamed",
                "renamed": True,
                "receipt": _receipt(
                    "updated",
                    [
                        {
                            "path": "Root/Renamed",
                            "op": "rename",
                            "before": "Old",
                            "after": "Renamed",
                        }
                    ],
                ),
            },
        )
    if command.command == "cmd_set_node_property":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": "Root",
                "property": "position",
                "value": {"x": 1.0, "y": 2.0},
                "set": True,
                "receipt": _receipt(
                    "updated",
                    [
                        {
                            "path": "Root",
                            "op": "set",
                            "before": {"x": 0.0, "y": 0.0},
                            "after": {"x": 1.0, "y": 2.0},
                        }
                    ],
                ),
            },
        )
    if command.command == "cmd_delete_node":
        return ResponseEnvelope.success(
            command.id,
            {
                "node_path": "Root/Gone",
                "deleted": True,
                "receipt": _receipt(
                    "updated",
                    [
                        {
                            "path": "Root/Gone",
                            "op": "remove",
                            "before": {"type": "Node", "name": "Gone"},
                            "after": None,
                        }
                    ],
                ),
            },
        )
    return _base(command)


async def _enable(client: Client[Any]) -> None:
    await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})


async def test_create_rename_set_delete_receipts_parse() -> None:
    async with Client(_server(_responder), mode="legacy") as client:
        await _enable(client)
        created = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": "Root", "node_type": "Node2D", "node_name": "New"},
        )
        renamed = await client.call_tool(
            "godot_scene_edit_rename_node",
            {"node_path": "Root/Old", "new_name": "Renamed"},
        )
        set_result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": "Root", "property": "position", "value": {"x": 1, "y": 2}},
        )
        deleted = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Root/Gone", "confirm": True},
        )
    assert created.structured_content["receipt"]["status"] == "created"
    assert created.structured_content["receipt"]["changes"][0]["op"] == "add"
    assert renamed.structured_content["receipt"]["changes"][0]["op"] == "rename"
    assert set_result.structured_content["receipt"]["changes"][0]["op"] == "set"
    assert deleted.structured_content["receipt"]["changes"][0]["op"] == "remove"


async def test_noop_receipt_is_honest_about_a_dropped_write() -> None:
    def dropped(command: Any) -> ResponseEnvelope | None:
        if command.command == "cmd_set_node_property":
            return ResponseEnvelope.success(
                command.id,
                {
                    "node_path": "Root",
                    "property": "position",
                    "value": {"x": 0.0, "y": 0.0},
                    "set": False,
                    "hint": "Setting 'position' did not land.",
                    "receipt": _receipt("noop"),
                },
            )
        return _responder(command)

    async with Client(_server(dropped), mode="legacy") as client:
        await _enable(client)
        result = await client.call_tool(
            "godot_scene_edit_set_node_property",
            {"node_path": "Root", "property": "position", "value": {"x": 1, "y": 2}},
        )
    payload = result.structured_content
    assert payload["set"] is False
    assert payload["receipt"]["status"] == "noop"
    assert payload["receipt"]["changes"] == []


def test_node_handlers_build_receipts_from_read_back() -> None:
    """Source-pin the addon side: the four core node handlers emit MCPReceipt."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "godot"
        / "addons"
        / "godot_mcp"
        / "handlers"
        / "mutation.gd"
    ).read_text(encoding="utf-8")
    for handler in (
        "_cmd_create_node",
        "_cmd_rename_node",
        "_cmd_set_node_property",
        "_cmd_delete_node",
    ):
        section = src.split(f"func {handler}", 1)[1].split("\nfunc ", 1)[0]
        assert "MCPReceipt.make(" in section, f"{handler} must emit a receipt"
    # A dropped write is `noop`, not `updated`.
    assert 'MCPReceipt.make("noop"' in src


async def test_batch_and_composite_receipts_parse() -> None:
    def responder(command: Any) -> ResponseEnvelope | None:
        if command.command == "cmd_batch_set_property":
            return ResponseEnvelope.success(
                command.id,
                {
                    "property": "visible",
                    "applied": ["S1", "S2"],
                    "skipped": [],
                    "count": 2,
                    "dry_run": False,
                    "undoable": True,
                    "persistence": [],
                    "hint": "",
                    "receipt": _receipt(
                        "updated",
                        [
                            {
                                "path": "S1",
                                "op": "set",
                                "before": True,
                                "after": False,
                            },
                            {
                                "path": "S2",
                                "op": "set",
                                "before": True,
                                "after": False,
                            },
                        ],
                    ),
                },
            )
        if command.command == "cmd_compose_node":
            return ResponseEnvelope.success(
                command.id,
                {
                    "node_path": "Trunk",
                    "created": True,
                    "children": ["Leaf"],
                    "script_attached": False,
                    "properties_set": [],
                    "saved": False,
                    "receipt": _receipt(
                        "created",
                        [
                            {
                                "path": "Trunk",
                                "op": "add",
                                "before": None,
                                "after": {"type": "Node2D", "name": "Trunk"},
                            },
                            {
                                "path": "Trunk/Leaf",
                                "op": "add",
                                "before": None,
                                "after": {"type": "Node2D", "name": "Leaf"},
                            },
                        ],
                    ),
                },
            )
        return _responder(command)

    async with Client(_server(responder), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "batch"})
        batch = await client.call_tool(
            "godot_batch_set_property",
            {"node_type": "Sprite2D", "property": "visible", "value": False},
        )
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        compose = await client.call_tool(
            "godot_composite_compose_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Trunk"},
        )
    assert batch.structured_content["receipt"]["status"] == "updated"
    assert len(batch.structured_content["receipt"]["changes"]) == 2
    assert compose.structured_content["receipt"]["status"] == "created"
    assert {c["path"] for c in compose.structured_content["receipt"]["changes"]} == {
        "Trunk",
        "Trunk/Leaf",
    }


async def test_resource_property_noop_receipt() -> None:
    """A dropped resource write is surfaced as set:false + a noop receipt."""

    def responder(command: Any) -> ResponseEnvelope | None:
        if command.command == "cmd_set_resource_property":
            return ResponseEnvelope.success(
                command.id,
                {
                    "resource_path": "res://shape.tres",
                    "property": "size",
                    "value": {"x": 4.0, "y": 5.0},
                    "set": False,
                    "hint": "Setting 'size' did not land.",
                    "receipt": _receipt("noop"),
                },
            )
        return _responder(command)

    async with Client(_server(responder), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "godot_resources_edit_set_resource_property",
            {"resource_path": "res://shape.tres", "property": "size", "value": {"x": 1, "y": 2}},
        )
    payload = result.structured_content
    assert payload["set"] is False
    assert payload["receipt"]["status"] == "noop"
    assert payload["receipt"]["changes"] == []


def test_resource_handlers_build_receipts_from_read_back() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
    resources = (root / "handlers" / "resources.gd").read_text(encoding="utf-8")
    assert 'MCPReceipt.make("noop"' in resources
    assert "ResourceLoader.load(path)" in resources
    scripts = (root / "handlers" / "scripts.gd").read_text(encoding="utf-8")
    assert "var landed := FileAccess.get_file_as_string(path)" in scripts
    assert "landed != content" in scripts


async def test_fallback_receipt_for_domains_without_handler_receipt() -> None:
    """The middleware fills a coarse receipt from the addon result + args."""

    def responder(command: Any) -> ResponseEnvelope | None:
        if command.command == "cmd_add_audio_bus":
            return ResponseEnvelope.success(
                command.id, {"index": 1, "name": command.params["name"]}
            )
        if command.command == "cmd_add_input_action":
            return ResponseEnvelope.success(
                command.id,
                {"name": command.params["name"], "added": True, "deadzone": 0.5},
            )
        return _responder(command)

    async with Client(_server(responder), mode="legacy") as client:
        await client.call_tool("godot_enable_toolset", {"category": "audio"})
        bus = await client.call_tool("godot_audio_add_bus", {"name": "Music"})
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        action = await client.call_tool("godot_input_map_add_action", {"name": "jump"})
    assert bus.structured_content["receipt"]["status"] == "created"
    assert bus.structured_content["receipt"]["changes"][0]["path"] == "Music"
    assert bus.structured_content["receipt"]["changes"][0]["op"] == "add"
    assert action.structured_content["receipt"]["status"] == "created"
    assert action.structured_content["receipt"]["changes"][0]["path"] == "jump"


def test_synthesize_receipt_status_and_op() -> None:
    from mcp_server.receipt_middleware import synthesize_receipt

    created = synthesize_receipt(
        "godot_audio_add_bus", {"name": "Music"}, {"index": 1, "name": "Music"}
    )
    assert created["status"] == "created" and created["changes"][0]["op"] == "add"
    dropped = synthesize_receipt(
        "godot_scene_edit_set_node_property",
        {"node_path": "Root", "property": "x"},
        {"node_path": "Root", "set": False},
    )
    assert dropped["status"] == "noop" and dropped["changes"] == []
    renamed = synthesize_receipt(
        "godot_scene_edit_rename_node",
        {"node_path": "Root/A", "new_name": "B"},
        {"node_path": "Root/B", "renamed": True},
    )
    assert renamed["changes"][0]["op"] == "rename"
    written = synthesize_receipt(
        "godot_resources_edit_create_resource",
        {"resource_path": "res://a.tres"},
        {"resource_path": "res://a.tres", "created": True},
    )
    assert written["changes"][0]["op"] == "write"


async def test_every_mutating_tool_is_receipt_covered() -> None:
    """Every mutating/destructive tool is covered by the receipt middleware (#756)."""
    from mcp_server.receipt_middleware import ReceiptMiddleware, synthesize_receipt

    server = _server(_responder)
    tools = await server.local_provider.list_tools()
    mutating = [
        t
        for t in tools
        if (t.meta or {}).get("safety_class") in ("mutating", "destructive")
    ]
    assert len(mutating) >= 90, f"expected the full mutating surface, got {len(mutating)}"
    assert any(isinstance(m, ReceiptMiddleware) for m in server.middleware), (
        "ReceiptMiddleware must be registered to fill fallback receipts"
    )
    for tool in mutating:
        receipt = synthesize_receipt(tool.name, {}, {})
        assert receipt["status"] in {"created", "updated", "existed", "noop"}
        assert isinstance(receipt["changes"], list)
