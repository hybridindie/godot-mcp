"""Contract tests for the `godot_describe_class` core tool (#533).

ClassDB metadata for agent discovery: describe a class's properties, methods,
signals, constants, enums, inheritance chain, and instantiability — with no
live node required. Drive the real FastMCP server over the in-memory client
with a fake addon peer carrying canned ClassDB responses.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# The canned ClassDB response the fake addon answers with (the addon reads the
# real ClassDB; the fake pins the envelope shape the server must map through).
# #564: `default` is the addon's Coerce.to_json VARIANT — a dict for Vector2/
# Color, raw int/float/bool otherwise, null when ClassDB has no stored default.
# It is NOT a string; the model must accept every JSON-safe Variant shape.
NODE2D = {
    "class_name": "Node2D",
    "inherits": "CanvasItem",
    "inherits_chain": ["Node2D", "CanvasItem", "Node", "Object"],
    "can_instantiate": True,
    "properties": [
        {"name": "position", "type": "Vector2", "default": {"x": 0.0, "y": 0.0}},
        {"name": "rotation", "type": "float", "default": 0.0},
        {"name": "visible", "type": "bool", "default": True},
        {"name": "modulate", "type": "Color", "default": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}},
        {"name": "texture_filter", "type": "int", "default": None},
    ],
    "methods": [
        {
            "name": "get_angle_to",
            "args": [{"name": "to_point", "type": "Vector2"}],
            "return_type": "float",
        },
    ],
    "signals": [{"name": "item_rect_changed", "args": []}],
    "constants": [{"name": "NOTIFICATION_ENTER_TREE", "value": 10, "enum": ""}],
    "enums": [],
}


def _class_responder(
    payload: dict[str, Any], known: list[str]
) -> Callable[[CommandEnvelope], ResponseEnvelope | None]:
    def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_describe_class":
            if cmd.params.get("class_name") in known:
                return ResponseEnvelope.success(cmd.id, payload)
            return ResponseEnvelope.failure(
                cmd.id,
                "VALIDATION_ERROR",
                f"Unknown class '{cmd.params.get('class_name')}'.",
            )
        return None

    return _responder


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_describe_class_forwards_with_flags() -> None:
    conn = FakeAddonConnection(responder=_class_responder(NODE2D, ["Node2D"]))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_describe_class", {"class_name": "Node2D"})
    assert conn.last_command().command == "cmd_describe_class"
    assert conn.last_command().params == {
        "class_name": "Node2D",
        "include_inherited": False,
        "include_private": False,
    }
    sc = result.structured_content
    assert sc["class_name"] == "Node2D"
    assert sc["can_instantiate"] is True
    # #564: defaults survive as the structured JSON Variant the addon sends —
    # not stringified. Each shape the addon's Coerce.to_json emits is pinned.
    props = {p["name"]: p for p in sc["properties"]}
    assert props["position"]["default"] == {"x": 0.0, "y": 0.0}
    assert props["rotation"]["default"] == 0.0
    assert props["visible"]["default"] is True
    assert props["modulate"]["default"] == {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    assert props["texture_filter"]["default"] is None
    assert sc["properties"][0]["type"] == "Vector2"
    assert sc["methods"][0]["name"] == "get_angle_to"
    assert sc["methods"][0]["args"][0]["name"] == "to_point"
    assert sc["signals"][0]["name"] == "item_rect_changed"
    assert sc["constants"][0]["name"] == "NOTIFICATION_ENTER_TREE"
    assert sc["inherits_chain"] == ["Node2D", "CanvasItem", "Node", "Object"]


async def test_describe_class_include_inherited_and_private_forwarded() -> None:
    conn = FakeAddonConnection(responder=_class_responder(NODE2D, ["Node2D"]))
    async with Client(_build(conn)) as client:
        await client.call_tool(
            "godot_describe_class",
            {"class_name": "Node2D", "include_inherited": True, "include_private": True},
        )
    assert conn.last_command().params == {
        "class_name": "Node2D",
        "include_inherited": True,
        "include_private": True,
    }


async def test_describe_class_unknown_class_raises_structured_error() -> None:
    conn = FakeAddonConnection(
        responder=_class_responder(NODE2D, ["Node2D", "Node3D", "Node"])
    )
    async with Client(_build(conn)) as client:
        with pytest.raises(ToolError, match="VALIDATION_ERROR"):
            await client.call_tool("godot_describe_class", {"class_name": "Node9D"})
    # The addon was asked once; the server did not pre-guess on the client side.
    assert conn.last_command().params["class_name"] == "Node9D"


async def test_describe_class_rejects_empty_class_name() -> None:
    conn = FakeAddonConnection(responder=_class_responder(NODE2D, ["Node2D"]))
    with pytest.raises(ToolError, match="class_name"):
        async with Client(_build(conn)) as client:
            await client.call_tool("godot_describe_class", {"class_name": ""})
    # Never sent: structured, pre-bridge.
    assert all(
        CommandEnvelope.model_validate_json(m).command != "cmd_describe_class"
        for m in conn.sent
    )