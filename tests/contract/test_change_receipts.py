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
