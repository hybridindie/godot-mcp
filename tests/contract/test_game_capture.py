"""Contract tests for the game frame capture tool (issue #446).

The game runs as a separate child process, so its viewport is reachable only via
the #66 runtime probe (in-process). Contract shape mirrors the editor screenshot
tool (issue #33): the addon dispatches one capture request per invocation, the
server polls the poll-and-cache command until a frame arrives, and the tool
decodes the base64 PNG into a FastMCP ``Image``.
"""

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
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8"
    "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_FRAME = {"format": "png", "width": 1, "height": 1, "base64": _PNG_B64}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_capture_game_screenshot":
        return ResponseEnvelope.success(cmd.id, {"ready": True, **_FRAME})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _server() -> FastMCP:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_gated_in_runtime_toolset() -> None:
    server, _ = _build_simple()
    async with Client(server, mode="legacy") as client:
        assert "godot_runtime_capture_game_screenshot" not in {
            t.name for t in await client.list_tools()
        }
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    assert "godot_runtime_capture_game_screenshot" in tools
    assert tools["godot_runtime_capture_game_screenshot"].meta["safety_class"] == "read_only"


def _build_simple() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_capture_returns_image_content() -> None:
    server, _ = _build_simple()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool("godot_runtime_capture_game_screenshot", {})
    image_blocks = [b for b in result.content if type(b).__name__ == "ImageContent"]
    assert image_blocks, f"expected an image content block, got {result.content}"
    block = image_blocks[0]
    assert block.mime_type == "image/png"
    assert base64.b64decode(block.data).startswith(b"\x89PNG\r\n\x1a\n")


async def test_frame_grab_polls_until_ready() -> None:
    """The probe answers asynchronously; the tool polls the addon's cache."""
    calls = {"n": 0}

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        calls["n"] += 1
        if calls["n"] == 1:
            return ResponseEnvelope.success(cmd.id, {"ready": False})
        return ResponseEnvelope.success(cmd.id, {"ready": True, **_FRAME})

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_capture_game_screenshot", {"timeout_ms": 2000}
        )
    assert calls["n"] >= 2
    image_blocks = [b for b in result.content if type(b).__name__ == "ImageContent"]
    assert image_blocks, f"expected an image content block, got {result.content}"


async def test_polls_send_a_stable_request_id() -> None:
    """The tool must carry a per-invocation request_id on every poll (Qodo #447 review):

    the addon dispatches one probe grab per request_id and matches the cached frame by
    it — polls without the key default to "" and never trigger the dispatch.
    """
    seen: list[str] = []

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        if cmd.command == "cmd_capture_game_screenshot":
            seen.append(str(cmd.params.get("request_id", "")))
            if len(seen) == 1:
                return ResponseEnvelope.success(cmd.id, {"ready": False})
            return ResponseEnvelope.success(cmd.id, {"ready": True, **_FRAME})
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool("godot_runtime_capture_game_screenshot", {"timeout_ms": 2000})
    assert seen, "capture command never sent"
    assert all(r for r in seen), f"empty request_id in polls: {seen}"
    assert len(set(seen)) == 1, f"request_id must be stable across polls: {seen}"


async def test_capture_never_ready_times_out_with_actionable_error() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"ready": False})

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_capture_game_screenshot", {"timeout_ms": 250}, raise_on_error=False
        )
    assert result.is_error
    assert "did not complete" in str(result.content)


async def test_no_play_session_is_structured_precondition_error() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        if cmd.command == "cmd_capture_game_screenshot":
            return ResponseEnvelope.failure(
                cmd.id, "PRECONDITION_FAILED", "No play session. Run play_scene first.",
                required="play_session",
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_capture_game_screenshot", {}, raise_on_error=False
        )
    assert result.is_error
    text = str(result.content)
    assert "PRECONDITION_FAILED" in text
    assert "play_session" in text


async def test_malformed_base64_is_structured_error() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(
            cmd.id, {"ready": True, "format": "png", "base64": "not!!valid!!"}
        )

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_capture_game_screenshot", {}, raise_on_error=False
        )
    assert result.is_error
    assert "base64" in str(result.content)