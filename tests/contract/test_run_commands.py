"""Contract tests for the run_commands batch envelope (issue #167).

A scripted harness collapses N independent bridge round-trips into one: the addon
executes the sub-commands in a single frame and returns one envelope per command.
These pin the typed I/O, the gated/mutating safety class, stop-on-error vs
continue, and that ``dry_run`` previews without sending the batch — driven by a
fake addon peer, no live editor.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _fake_run_commands(p: dict[str, Any]) -> dict[str, Any]:
    """Simulate the addon executing each sub-command in one frame, in order."""
    results: list[dict[str, Any]] = []
    ok_all = True
    for entry in p.get("commands", []):
        cmd = entry.get("command", "")
        is_ghost = entry.get("params", {}).get("node_path") == "Ghost"
        if cmd == "cmd_set_node_property" and is_ghost:
            results.append(
                {"command": cmd, "ok": False, "error": "RESOURCE_NOT_FOUND", "hint": "No node."}
            )
            ok_all = False
            if p.get("stop_on_error", True):
                break
        else:
            results.append({"command": cmd, "ok": True, "result": {"echo": cmd}})
    return {"results": results, "ok_all": ok_all, "count": len(results)}


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_run_commands":
        return ResponseEnvelope.success(cmd.id, _fake_run_commands(cmd.params))
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_run_commands_is_gated_mutating() -> None:
    server, _ = _build()
    async with Client(server) as client:
        before = {t.name for t in await client.list_tools()}
        assert "run_commands" not in before, "run_commands must be gated off by default"
        await client.call_tool("enable_toolset", {"category": "composite"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["run_commands"].meta["safety_class"] == "mutating"


async def test_run_commands_executes_batch_in_one_round_trip() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "run_commands",
            {
                "commands": [
                    {"command": "cmd_create_node", "params": {"parent_path": ".", "name": "A"}},
                    {"command": "set_node_property", "params": {"node_path": "A"}},
                ]
            },
        )
    data = result.structured_content
    assert data["ok_all"] is True
    assert data["count"] == 2
    # bare names are normalized to the addon cmd_* form
    assert [r["command"] for r in data["results"]] == ["cmd_create_node", "cmd_set_node_property"]
    # N sub-commands collapse into ONE bridge round-trip
    assert _commands(conn).count("cmd_run_commands") == 1
    assert "cmd_create_node" not in _commands(conn)  # not sent individually


async def test_run_commands_stop_on_error_truncates() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "run_commands",
            {
                "commands": [
                    {"command": "cmd_set_node_property", "params": {"node_path": "Ghost"}},
                    {"command": "cmd_set_node_property", "params": {"node_path": "A"}},
                ],
                "stop_on_error": True,
            },
        )
    data = result.structured_content
    assert data["ok_all"] is False
    assert data["count"] == 1  # stopped after the first failure
    assert data["results"][0]["error"] == "RESOURCE_NOT_FOUND"


async def test_run_commands_continue_on_error_runs_all() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "run_commands",
            {
                "commands": [
                    {"command": "cmd_set_node_property", "params": {"node_path": "Ghost"}},
                    {"command": "cmd_set_node_property", "params": {"node_path": "A"}},
                ],
                "stop_on_error": False,
            },
        )
    data = result.structured_content
    assert data["ok_all"] is False
    assert data["count"] == 2  # both ran despite the first failing
    assert data["results"][1]["ok"] is True


async def test_run_commands_dry_run_sends_nothing() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "run_commands",
            {
                "commands": [
                    {"command": "cmd_create_node", "params": {"parent_path": ".", "name": "A"}}
                ],
                "dry_run": True,
            },
        )
    data = result.structured_content
    assert data["dry_run"] is True
    assert data["planned"] == ["cmd_create_node"]
    assert data["count"] == 1
    assert "cmd_run_commands" not in _commands(conn)


async def test_run_commands_rejects_nesting() -> None:
    # #167 review: a nested run_commands would recurse the editor dispatch and crash
    # it. The server rejects the batch up front (either bare or cmd_ form), sending nothing.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "run_commands",
            {"commands": [{"command": "run_commands", "params": {"commands": []}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "nested" in str(result.content).lower()
    assert "cmd_run_commands" not in _commands(conn)  # nothing sent
