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
    async with Client(server, mode="legacy") as client:
        before = {t.name for t in await client.list_tools()}
        assert "godot_composite_run_commands" not in before, (
            "run_commands must be gated off by default"
        )
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["godot_composite_run_commands"].meta["safety_class"] == "mutating"


async def test_run_commands_executes_batch_in_one_round_trip() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
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
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
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
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
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
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
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
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "run_commands", "params": {"commands": []}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "nested" in str(result.content).lower()
    assert "cmd_run_commands" not in _commands(conn)  # nothing sent


async def test_run_commands_resolves_trimmed_tool_names() -> None:
    # #420: exposed names whose action is trimmed by the godot_ transform
    # (e.g. godot_physics_set_layers -> "physics_set_layers") must resolve to
    # the real addon handler (cmd_set_physics_layers), not the nonexistent
    # cmd_set_layers. The documented bare form is the exposed name minus "godot_".
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {"command": "physics_set_layers", "params": {"node_path": "Body"}},
                    {
                        "command": "particles_apply_preset",
                        "params": {"node_path": "P", "preset": "smoke"},
                    },
                    {"command": "write_script", "params": {"script_path": "res://a.gd"}},
                    {"command": "capture_screenshot", "params": {}},
                ]
            },
        )
    data = result.structured_content
    assert data["ok_all"] is True
    assert [r["command"] for r in data["results"]] == [
        "cmd_set_physics_layers",
        "cmd_apply_particle_preset",
        "cmd_write_script",
        "cmd_capture_editor_screenshot",
    ]


async def test_run_commands_ambiguous_bare_name_lists_matches() -> None:
    # #420: "set_layers" is genuinely ambiguous (navigation_set_layers vs
    # physics_set_layers) — fail up front naming both, instead of leaking a
    # bogus cmd_set_layers to the addon.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "set_layers", "params": {}}]},
            raise_on_error=False,
        )
    assert result.is_error
    text = str(result.content)
    assert "navigation_set_layers" in text and "physics_set_layers" in text
    assert "cmd_set_layers" not in _commands(conn)  # nothing sent


async def test_run_commands_resolves_reordered_read_names() -> None:
    # #420 (read half): tools whose bare name reorders words vs the handler
    # (audio_add_bus -> add_audio_bus, get_bus_layout -> get_audio_bus_layout,
    #  read_shader -> read_shader, get_shader_param -> get_shader_param).
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {"command": "add_bus", "params": {"name": "SFX"}},
                    {"command": "get_bus_layout", "params": {}},
                    {"command": "read_shader", "params": {"shader_path": "res://a.gdshader"}},
                    {"command": "get_shader_param", "params": {"node_path": "X", "name": "y"}},
                ]
            },
        )
    data = result.structured_content
    assert data["ok_all"] is True
    assert [r["command"] for r in data["results"]] == [
        "cmd_add_audio_bus",
        "cmd_get_audio_bus_layout",
        "cmd_read_shader",
        "cmd_get_shader_param",
    ]


async def test_run_commands_maps_create_node_node_name() -> None:
    # #421: the create_node tool maps node_name -> addon's "name" key. run_commands
    # must apply the same translation, or the addon silently falls back to the
    # type name (the reported "create_node ignores node_name" symptom).
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {
                        "command": "create_node",
                        "params": {
                            "parent_path": ".",
                            "node_type": "Area3D",
                            "node_name": "DetectionArea",
                        },
                    },
                    {
                        "command": "cmd_create_node",
                        "params": {
                            "parent_path": ".",
                            "node_type": "Area3D",
                            "node_name": "AlsoMapped",
                        },
                    },
                ]
            },
        )
    data = result.structured_content
    assert data["ok_all"] is True
    sent = CommandEnvelope.model_validate_json(conn.sent[-1])
    batch = sent.params["commands"]
    assert batch[0]["params"] == {
        "parent_path": ".",
        "node_type": "Area3D",
        "name": "DetectionArea",
    }
    assert batch[1]["params"]["name"] == "AlsoMapped"


async def test_run_commands_unknown_bare_name_fails_with_suggestion() -> None:
    # #420: a bare name that matches no tool must fail the batch up front with the
    # closest real name in the hint — not leak into the addon as cmd_<garbage>.
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "set_layerz", "params": {}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "set_layers" in str(result.content)  # suggests the real bare name
    assert "cmd_set_layerz" not in _commands(conn)  # nothing sent to the addon
