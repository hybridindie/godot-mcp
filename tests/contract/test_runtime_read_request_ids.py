"""Contract tests: probe-backed runtime reads carry a request id (issue #670).

`get_game_scene_tree` and `get_performance_monitors` used to serve the *previous*
call's cached value. The fix mirrors the `find_ui`/`read_property` pattern: the
server sends a per-invocation `request_id`, the addon returns ``ready:false``
until the probe's reply for that id lands, and the server polls until it does.

Driven by a fake addon peer that only becomes ready on the second poll for a
given id, and encodes the id into the payload — so a server that returns the
prior request's value fails.
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


class _ProbePeer:
    """Fake addon peer: pending on the first poll for a request id, ready after.

    The ready payload echoes the request id, so a caller that returns the wrong
    (prior) request's result is caught.
    """

    def __init__(self) -> None:
        self.polls: dict[str, int] = {}
        self.ids: list[str] = []

    def responder(self, cmd: CommandEnvelope) -> ResponseEnvelope | None:
        match cmd.command:
            case "cmd_get_game_scene_tree":
                rid = str(cmd.params.get("request_id", ""))
                self._count(rid)
                if self.polls[rid] < 2:
                    return ResponseEnvelope.success(
                        cmd.id,
                        {
                            "playing": True,
                            "connected": True,
                            "ready": False,
                            "reason": "scene_tree_pending",
                            "tree": None,
                        },
                    )
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "playing": True,
                        "connected": True,
                        "ready": True,
                        # Encode the request id so the test can prove freshness.
                        "tree": {"name": rid, "type": "Window", "path": "/root", "children": []},
                    },
                )
            case "cmd_get_performance_monitors":
                rid = str(cmd.params.get("request_id", ""))
                self._count(rid)
                if self.polls[rid] < 2:
                    return ResponseEnvelope.success(
                        cmd.id,
                        {
                            "playing": True,
                            "connected": True,
                            "ready": False,
                            "reason": "probe_pending",
                            "monitors": {},
                        },
                    )
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "playing": True,
                        "connected": True,
                        "ready": True,
                        # fps encodes a per-request ordinal so a stale read fails.
                        "monitors": {"fps": float(len(self.ids)), "node_count": 1.0},
                    },
                )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    def _count(self, rid: str) -> None:
        if rid not in self.polls:
            self.polls[rid] = 0
            self.ids.append(rid)
        self.polls[rid] += 1


def _build() -> tuple[FastMCP, FakeAddonConnection, _ProbePeer]:
    peer = _ProbePeer()
    conn = FakeAddonConnection(responder=peer.responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn, peer


def _sent_ids(conn: FakeAddonConnection, command: str) -> list[str]:
    return [
        str(CommandEnvelope.model_validate_json(s).params.get("request_id", ""))
        for s in conn.sent
        if CommandEnvelope.model_validate_json(s).command == command
    ]


async def test_scene_tree_calls_are_request_scoped() -> None:
    server, conn, peer = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        first = await client.call_tool("godot_runtime_get_game_scene_tree", {})
        second = await client.call_tool("godot_runtime_get_game_scene_tree", {})
    # Each call must carry its own fresh request_id...
    ids = _sent_ids(conn, "cmd_get_game_scene_tree")
    assert len(set(ids)) == 2, "each invocation must use a distinct request_id"
    # ...and return the tree the peer produced for THAT id (never the prior call's).
    assert first.structured_content["tree"]["name"] == ids[0]
    assert second.structured_content["tree"]["name"] == ids[-1]
    assert first.structured_content["tree"]["name"] != second.structured_content["tree"]["name"]
    # The server polled the pending reply until it became ready.
    assert peer.polls[ids[0]] >= 2


async def test_performance_monitors_calls_are_request_scoped() -> None:
    server, conn, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "profiling"})
        first = await client.call_tool("godot_profiling_get_performance_monitors", {})
        second = await client.call_tool("godot_profiling_get_performance_monitors", {})
    ids = _sent_ids(conn, "cmd_get_performance_monitors")
    assert len(set(ids)) == 2
    # First invocation's ordinal is 1, the second's is 2 (never the prior value).
    assert first.structured_content["monitors"]["fps"] == 1.0
    assert second.structured_content["monitors"]["fps"] == 2.0


# --- addon/probe source pins (the GDScript side) ----------------------------


def _addon_src(name: str) -> str:
    from pathlib import Path

    return (Path("godot/addons/godot_mcp") / name).read_text(encoding="utf-8")


def test_probe_echoes_request_id_for_probe_backed_reads() -> None:
    src = _addon_src("mcp_runtime_probe.gd")
    tree = src.split('"get_scene_tree":', 1)[1].split("return true", 1)[0]
    perf = src.split('"get_performance":', 1)[1].split("return true", 1)[0]
    assert "request_id" in tree, "scene_tree reply must echo request_id (#670)"
    assert "request_id" in perf, "performance reply must echo request_id (#670)"


def test_addon_gates_caches_on_the_request_id() -> None:
    src = _addon_src("mcp_debugger.gd")
    assert "_scene_tree_request" in src and "_performance_request" in src
    assert '_scene_tree_request' in src  # gate present
    assert "request_id" in src


def test_handlers_read_the_request_id() -> None:
    for file in ("handlers/runtime_session.gd", "handlers/profiling.gd"):
        src = _addon_src(file)
        assert 'params.get("request_id"' in src, f"{file} must read request_id (#670)"
