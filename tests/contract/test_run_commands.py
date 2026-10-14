"""Contract tests for the run_commands batch envelope (issue #167).

A scripted harness collapses N independent bridge round-trips into one: the addon
executes the sub-commands in a single frame and returns one envelope per command.
These pin the typed I/O, the gated/mutating safety class, stop-on-error vs
continue, and that ``dry_run`` previews without sending the batch — driven by a
fake addon peer, no live editor.

Issue #634 adds the per-entry safety contract: a batch is not a way around the
toolset gate, the destructive ``confirm`` gate, or the server path preflight.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalRequest, ApprovalResponse
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.safety import ApprovalGate
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _fake_run_commands(p: dict[str, Any]) -> dict[str, Any]:
    """Simulate the addon executing each sub-command in one frame, in order.

    #461: the addon now reports honest partial completion — when ``stop_on_error``
    halts the batch, the response names the index of the failing command
    (``aborted_at``) and counts the skipped trailing commands.
    """
    results: list[dict[str, Any]] = []
    ok_all = True
    aborted_at: int | None = None
    commands = p.get("commands", [])
    for i, entry in enumerate(commands):
        cmd = entry.get("command", "")
        is_ghost = entry.get("params", {}).get("node_path") == "Ghost"
        if cmd == "cmd_set_node_property" and is_ghost:
            results.append(
                {"command": cmd, "ok": False, "error": "RESOURCE_NOT_FOUND", "hint": "No node."}
            )
            ok_all = False
            aborted_at = i
            if p.get("stop_on_error", True):
                break
        else:
            results.append({"command": cmd, "ok": True, "result": {"echo": cmd}})
    out: dict[str, Any] = {"results": results, "ok_all": ok_all, "count": len(results)}
    if aborted_at is not None and p.get("stop_on_error", True):
        out["aborted_at"] = aborted_at
        out["skipped_count"] = len(commands) - (aborted_at + 1)
        out["hint"] = (
            f"Batch stopped at command {aborted_at}; "
            f"{len(commands) - (aborted_at + 1)} later commands were not run — the "
            "scene may be unsaved. Re-run the remaining commands with "
            "stop_on_error=false or fix the failing command first."
        )
    return out


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_run_commands":
        return ResponseEnvelope.success(cmd.id, _fake_run_commands(cmd.params))
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build(approval: ApprovalGate | None = None) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge, approval=approval), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def _enable(client: Any, *categories: str) -> None:
    """Enable the given toolsets (the batch's sub-commands are gated per their
    own toolset, #634)."""
    for category in categories:
        await client.call_tool("godot_enable_toolset", {"category": category})


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
        await _enable(client, "composite", "scene_edit")
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
        await _enable(client, "composite", "scene_edit")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {"command": "cmd_set_node_property", "params": {"node_path": "Ghost"}},
                    {"command": "cmd_set_node_property", "params": {"node_path": "A"}},
                    {"command": "cmd_save_scene", "params": {}},
                ],
                "stop_on_error": True,
            },
        )
    data = result.structured_content
    assert data["ok_all"] is False
    assert data["count"] == 1  # stopped after the first failure
    assert data["results"][0]["error"] == "RESOURCE_NOT_FOUND"
    # #461: partial completion is named, never silent — which command aborted the
    # batch, how many were skipped, and the unsaved-scene consequence.
    assert data["aborted_at"] == 0
    assert data["skipped_count"] == 2
    assert "may be unsaved" in data["hint"]
    assert "2 later commands were not run" in data["hint"]


async def test_run_commands_continue_on_error_reports_no_abort() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
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
    # #461: nothing was skipped, so the abort fields stay absent/None.
    assert data.get("aborted_at") in (None, {})
    assert not data.get("hint")


async def test_run_commands_dry_run_sends_nothing() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
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
        await _enable(client, "composite", "physics", "particles", "scripts", "editor")
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
        await _enable(client, "composite", "audio", "shader")
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
        await _enable(client, "composite", "scene_edit")
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


# ---------------------------------------------------------------- safety (#634)
#
# A run_commands batch must not be a safety bypass: each sub-command is resolved
# back to its exposed tool and inherits that tool's toolset (gating), path
# preflight, and safety class (destructive needs confirm + approval). The outer
# tool being ``mutating`` is not a license to smuggle a destructive command.


async def test_run_commands_destructive_subcommand_without_confirm_refused() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "cmd_delete_node", "params": {"node_path": "Player"}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "confirm" in str(result.content).lower()
    assert "cmd_run_commands" not in _commands(conn)  # nothing sent


async def test_run_commands_destructive_subcommand_with_confirm_runs() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [{"command": "cmd_delete_node", "params": {"node_path": "Player"}}],
                "confirm": True,
            },
        )
    assert result.structured_content["ok_all"] is True
    assert "cmd_run_commands" in _commands(conn)


async def test_run_commands_gated_toolset_subcommand_refused() -> None:
    # Only ``composite`` is enabled; cmd_create_node belongs to ``scene_edit``.
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "cmd_create_node", "params": {"parent_path": "."}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "not enabled" in str(result.content)
    assert "scene_edit" in str(result.content)
    assert "cmd_run_commands" not in _commands(conn)


async def test_run_commands_path_traversal_subcommand_refused() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scripts")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {
                        "command": "cmd_write_script",
                        "params": {"script_path": "res://../evil.gd", "content": "extends Node"},
                    }
                ]
            },
            raise_on_error=False,
        )
    assert result.is_error
    assert "res://" in str(result.content)
    assert "cmd_run_commands" not in _commands(conn)


async def test_run_commands_unknown_cmd_refused() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite")
        result = await client.call_tool(
            "godot_composite_run_commands",
            {"commands": [{"command": "cmd_not_a_real_command", "params": {}}]},
            raise_on_error=False,
        )
    assert result.is_error
    assert "not_a_real_command" in str(result.content)
    assert "cmd_run_commands" not in _commands(conn)


async def test_run_commands_dry_run_reports_resolved_policy() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
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
    assert "cmd_run_commands" not in _commands(conn)
    plan = data["plan"]
    assert plan[0]["command"] == "cmd_create_node"
    assert plan[0]["tool"] == "godot_scene_edit_create_node"
    assert plan[0]["toolset"] == "scene_edit"
    assert plan[0]["safety_class"] == "mutating"


async def test_run_commands_batch_with_destructive_entry_is_destructive_to_webhook() -> None:
    # A batch containing a destructive entry must be classified destructive at
    # the approval boundary — not mutating — so the webhook sees the real risk.
    seen: dict[str, Any] = {}

    async def approve(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
        seen["safety_class"] = request.safety_class
        seen["action"] = request.action
        return ApprovalResponse(approved=True)

    gate = ApprovalGate(webhook_url="http://hook", poster=approve)
    server, conn = _build(approval=gate)
    async with Client(server) as client:
        await _enable(client, "composite", "scene_edit")
        await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [{"command": "cmd_delete_node", "params": {"node_path": "Player"}}],
                "confirm": True,
            },
        )
    assert seen["safety_class"] == "destructive"
    assert "cmd_run_commands" in _commands(conn)
