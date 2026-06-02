"""Contract tests for the editor screenshot tool (issue #33)."""

from __future__ import annotations

import base64

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
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
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
    async with Client(_server()) as client:
        assert "capture_editor_screenshot" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "editor"})
        tools = {t.name: t for t in await client.list_tools()}
    assert "capture_editor_screenshot" in tools
    assert tools["capture_editor_screenshot"].meta["safety_class"] == "read_only"


async def test_capture_returns_image_content() -> None:
    async with Client(_server()) as client:
        await client.call_tool("enable_toolset", {"category": "editor"})
        result = await client.call_tool("capture_editor_screenshot", {})
    image_blocks = [b for b in result.content if type(b).__name__ == "ImageContent"]
    assert image_blocks, f"expected an image content block, got {result.content}"
    block = image_blocks[0]
    assert block.mimeType == "image/png"
    # The returned data decodes to the same PNG bytes the addon supplied.
    assert base64.b64decode(block.data).startswith(b"\x89PNG\r\n\x1a\n")
