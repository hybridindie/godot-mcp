"""Contract tests: debugger Tier-2 reads carry a request id (issue #671).

`evaluate_expression`, `get_stack_frames`, and `get_frame_variables` used to
serve the *previous* call's cached reply (labelled as current). The fix tags each
engine-debugger reply with the in-flight request id; the server sends a
per-invocation id and polls until the matching reply lands.

Driven by a fake addon peer that only becomes ready on the second poll for an id
and echoes the id into the payload — so a server that returns the prior request's
value fails.
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


class _DebuggerPeer:
    def __init__(self) -> None:
        self.polls: dict[str, int] = {}
        self.ids: list[str] = []

    def _count(self, rid: str) -> None:
        if rid not in self.polls:
            self.polls[rid] = 0
            self.ids.append(rid)
        self.polls[rid] += 1

    def _pending(self, cmd: CommandEnvelope, reason: str) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"ready": False, "reason": reason})

    def responder(self, cmd: CommandEnvelope) -> ResponseEnvelope | None:
        rid = str(cmd.params.get("request_id", ""))
        match cmd.command:
            case "cmd_evaluate_expression":
                self._count(rid)
                if self.polls[rid] < 2:
                    return self._pending(cmd, "evaluation_pending")
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "ready": True,
                        "expression": cmd.params.get("expression", ""),
                        # Echo the request id as the value so a stale read fails.
                        "value": rid,
                        "evaluated": True,
                    },
                )
            case "cmd_get_stack_frames":
                self._count(rid)
                if self.polls[rid] < 2:
                    return self._pending(cmd, "stack_pending")
                return ResponseEnvelope.success(
                    cmd.id, {"ready": True, "frames": [{"file": rid, "line": 1, "func": "f"}]}
                )
            case "cmd_get_frame_variables":
                self._count(rid)
                if self.polls[rid] < 2:
                    return self._pending(cmd, "frame_vars_pending")
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "ready": True,
                        "locals": [{"name": rid, "value": 1}],
                        "members": [],
                        "globals": [],
                    },
                )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection, _DebuggerPeer]:
    peer = _DebuggerPeer()
    conn = FakeAddonConnection(responder=peer.responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn, peer


def _ids(conn: FakeAddonConnection, command: str) -> list[str]:
    return [
        str(CommandEnvelope.model_validate_json(s).params.get("request_id", ""))
        for s in conn.sent
        if CommandEnvelope.model_validate_json(s).command == command
    ]


async def test_two_evaluations_return_their_own_value() -> None:
    server, conn, peer = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        first = await client.call_tool(
            "godot_debugger_evaluate_expression", {"expression": "1 + 1"}
        )
        second = await client.call_tool(
            "godot_debugger_evaluate_expression", {"expression": "2 + 2"}
        )
    ids = _ids(conn, "cmd_evaluate_expression")
    assert len(set(ids)) == 2, "each invocation must use a distinct request_id"
    # Each call returns the value the peer produced for ITS request id.
    assert first.structured_content["value"] == ids[0]
    assert second.structured_content["value"] == ids[-1]
    assert first.structured_content["value"] != second.structured_content["value"]
    assert first.structured_content["expression"] == "1 + 1"
    assert peer.polls[ids[0]] >= 2  # polled the pending reply until ready


async def test_stack_frames_are_request_scoped() -> None:
    server, conn, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        first = await client.call_tool("godot_debugger_get_stack_frames", {})
        second = await client.call_tool("godot_debugger_get_stack_frames", {})
    ids = _ids(conn, "cmd_get_stack_frames")
    assert len(set(ids)) == 2
    assert first.structured_content["frames"][0]["file"] == ids[0]
    assert second.structured_content["frames"][0]["file"] == ids[-1]


async def test_frame_variables_are_request_scoped() -> None:
    server, conn, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        first = await client.call_tool("godot_debugger_get_frame_variables", {})
        second = await client.call_tool("godot_debugger_get_frame_variables", {})
    ids = _ids(conn, "cmd_get_frame_variables")
    assert len(set(ids)) == 2
    assert first.structured_content["locals"][0]["name"] == ids[0]
    assert second.structured_content["locals"][0]["name"] == ids[-1]


# --- addon source pins ------------------------------------------------------


def _addon_src(name: str) -> str:
    from pathlib import Path

    return (Path("godot/addons/godot_mcp") / name).read_text(encoding="utf-8")


def test_addon_tags_debugger_replies_with_the_request_id() -> None:
    src = _addon_src("mcp_debugger.gd")
    for var in ("_evaluation_request", "_stack_request", "_frame_vars_request"):
        assert var in src, f"{var} missing (#671)"
    for capture in ('"evaluation_return":', '"stack_dump":'):
        block = src.split(capture, 1)[1].split("return true", 1)[0]
        assert "request_id" in block, f"{capture} must tag the reply with request_id"


def test_handlers_read_the_request_id() -> None:
    src = _addon_src("handlers/debugger.gd")
    assert src.count('params.get("request_id"') >= 3, (
        "evaluate/stack/frame_vars handlers must read request_id (#671)"
    )
