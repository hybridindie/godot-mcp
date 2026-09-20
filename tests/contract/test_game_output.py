"""Contract tests for the game console output capture (issue #534).

The probe captures the running game's print()/push_error()/push_warning()
stream via a custom Logger (OS.add_logger) into a bounded ring buffer, relays
it over the ``godot_mcp:game_output`` debugger channel, and the addon caches
it (poll-and-cache, same as scene tree/performance). ``godot_runtime_get_game_output``
serves it read-only with a ``since_seq`` cursor for incremental pulls — the
agent finally reads crash traces and log-based assertions during a play-test.

The addon/probe are GDScript: their envelope shapes are pinned by the source
scan + live smokes (``godot/tests/game_output_smoke.gd`` + the e2e suite);
this file pins the *server* tool surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_OUTPUT: dict[str, Any] = {
    "next_seq": 7,
    "total": 7,
    "dropped": 2,
    "entries": [
        {"seq": 5, "kind": "stdout", "text": "level loaded", "time_ms": 120.0},
        {"seq": 6, "kind": "error", "text": "Invalid get index 'hp'", "time_ms": 200.0},
        {"seq": 7, "kind": "warning", "text": "deprecated call", "time_ms": 210.0},
    ],
}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_get_game_output":
        since = int(cmd.params.get("since_seq", 0))
        all_entries: list[dict[str, Any]] = _OUTPUT["entries"]
        entries = [e for e in all_entries if e["seq"] > since]
        return ResponseEnvelope.success(
            cmd.id,
            {
                "playing": True,
                "connected": True,
                "entries": entries,
                "next_seq": _OUTPUT["next_seq"],
                "total": _OUTPUT["total"],
                "dropped": _OUTPUT["dropped"],
            },
        )
    from tests.contract.test_runtime_session import _responder as runtime_responder

    return runtime_responder(cmd)


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_gated_in_runtime_toolset_read_only() -> None:
    server, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_runtime_get_game_output" not in {t.name for t in await client.list_tools()}
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_runtime_get_game_output"].meta["safety_class"] == "read_only"


async def test_get_output_returns_entries_and_honesty_counts() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool("godot_runtime_get_game_output", {})
    sc = result.structured_content
    assert sc["connected"] is True
    assert sc["next_seq"] == 7
    assert sc["total"] == 7
    assert sc["dropped"] == 2  # honest: 2 entries were evicted by the ring
    kinds = {e["kind"] for e in sc["entries"]}
    assert kinds == {"stdout", "error", "warning"}


async def test_get_output_since_seq_cursor() -> None:
    """Incremental pulls: since_seq=6 returns only entries after 6."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool("godot_runtime_get_game_output", {"since_seq": 6})
    sc = result.structured_content
    assert [e["seq"] for e in sc["entries"]] == [7]
    # The cursor param reached the addon.
    assert sc["next_seq"] == 7


async def test_get_output_source_sends_the_probe_query() -> None:
    """The tool routes to cmd_get_game_output (poll-and-cache, not a push)."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool("godot_runtime_get_game_output", {})
    sent = [CommandEnvelope.model_validate_json(s).command for s in conn.sent]
    assert "cmd_get_game_output" in sent


# -- addon side (source-scanned per the established pattern) ------------------


def _addon_root() -> Path:
    return Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def test_probe_registers_a_logger_and_relays_the_ring() -> None:
    probe_src = _addon_root() / "mcp_runtime_probe.gd"
    src = probe_src.read_text()
    # A custom Logger captures the game's output stream (print/push_error/...).
    assert "OS.add_logger" in src, "probe must register a custom Logger (issue #534)"
    assert "_log_message" in src and "_log_error" in src
    # The ring is bounded (honest eviction, never unbounded growth).
    assert "MAX_OUTPUT" in src
    # The editor can pull the ring on demand via the godot_mcp channel.
    assert '"get_output"' in src
    assert "godot_mcp:game_output" in src


def test_debugger_caches_the_output_ring() -> None:
    debugger_src = _addon_root() / "mcp_debugger.gd"
    src = debugger_src.read_text()
    assert "godot_mcp:game_output" in src, "MCPDebugger must cache the relayed ring"
    assert "get_game_output" in src


def test_router_registers_cmd_get_game_output() -> None:
    handler_src = (_addon_root() / "handlers" / "runtime_session.gd").read_text()
    assert 'handlers["cmd_get_game_output"]' in handler_src
    # Served from the poll-and-cache — and readable while broken (#411/#446
    # parity: output is the most useful thing to read during a break).
    assert "cmd_get_game_output" in handler_src
