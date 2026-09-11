"""Contract tests for the editor screenshot tool (issue #33)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# 1x1 red PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8"
    "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_capture_editor_screenshot":
        return ResponseEnvelope.success(
            cmd.id, {"format": "png", "width": 1, "height": 1, "base64": _PNG_B64}
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _server() -> FastMCP:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_gated_in_editor_toolset() -> None:
    async with Client(_server(), mode="legacy") as client:
        assert "godot_editor_capture_screenshot" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        tools = {t.name: t for t in await client.list_tools()}
    assert "godot_editor_capture_screenshot" in tools
    assert tools["godot_editor_capture_screenshot"].meta["safety_class"] == "read_only"


async def test_malformed_base64_is_structured_error() -> None:
    def bad(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"format": "png", "base64": "not!!valid!!"})

    conn = FakeAddonConnection(responder=bad)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool("godot_editor_capture_screenshot", {}, raise_on_error=False)
    assert result.is_error
    assert "base64" in str(result.content)


async def test_capture_returns_image_content() -> None:
    async with Client(_server()) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool("godot_editor_capture_screenshot", {})
    image_blocks = [b for b in result.content if type(b).__name__ == "ImageContent"]
    assert image_blocks, f"expected an image content block, got {result.content}"
    block = image_blocks[0]
    assert block.mime_type == "image/png"
    # The returned data decodes to the same PNG bytes the addon supplied.
    assert base64.b64decode(block.data).startswith(b"\x89PNG\r\n\x1a\n")


async def test_deferred_capture_polls_until_ready() -> None:
    """Two-phase addon (grab pending → done): the tool polls and still returns the image."""
    calls = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        calls["n"] += 1
        if calls["n"] == 1:
            return ResponseEnvelope.success(cmd.id, {"ready": False})
        return ResponseEnvelope.success(
            cmd.id,
            {"ready": True, "format": "png", "width": 1, "height": 1, "base64": _PNG_B64},
        )

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    async with Client(create_server(ServerConfig(), bridge=bridge)) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool("godot_editor_capture_screenshot", {"timeout_ms": 2000})
    assert calls["n"] >= 2
    image_blocks = [b for b in result.content if type(b).__name__ == "ImageContent"]
    assert image_blocks, f"expected an image content block, got {result.content}"


async def test_capture_never_ready_times_out_with_actionable_error() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"ready": False})

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    async with Client(create_server(ServerConfig(), bridge=bridge)) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool(
            "godot_editor_capture_screenshot", {"timeout_ms": 250}, raise_on_error=False
        )
    assert result.is_error
    assert "did not complete" in str(result.content)


async def test_addon_reason_surfaces_in_timeout_error() -> None:
    """#416: the addon self-reports why the editor isn't cooperating
    ({ready: false, pending: true, reason: "editor_not_drawing"}); the tool's
    expiry error must relay that reason instead of the bridge's generic
    "no response from Godot" — the agent needs the actual cause."""
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(
            cmd.id, {"ready": False, "pending": True, "reason": "editor_not_drawing"}
        )

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    async with Client(create_server(ServerConfig(), bridge=bridge)) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool(
            "godot_editor_capture_screenshot", {"timeout_ms": 250}, raise_on_error=False
        )
    assert result.is_error
    text = str(result.content)
    assert "editor_not_drawing" in text
    assert "bridge" not in text.lower() or "not rendering" in text.lower()


def test_editor_capture_state_is_reset_per_grab() -> None:
    """Qodo #457 round-2: `_shot`/`_grab_queued`/`_pending_polls` are shared across
    concurrent capture invocations. The handler must reset all three whenever it
    returns a completed shot, so a second capture can't read the first's payload
    or inherit a stale grace counter."""
    src = (
        Path(__file__).resolve().parents[2] / "godot/addons/godot_mcp/handlers/editor.gd"
    ).read_text()
    handler = src.split("func _cmd_capture_editor_screenshot", 1)[1].split("\nfunc ", 1)[0]
    assert "_pending_polls = 0" in handler  # counter reset on the ready path
    assert "_grab_queued = false" in handler  # queued flag reset on the ready path
    # The grace counter must also reset when a NEW grab is queued, so a stale
    # counter from a prior invocation can't shorten the next one's grace window.
    assert "if not _grab_queued" in handler
    body_after_queue = handler.split("if not _grab_queued", 1)[1]
    assert "_pending_polls = 0" in body_after_queue
