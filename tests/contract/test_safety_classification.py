"""Contract tests pinning the safety-class audit (issue #638).

The classification rule (see docs/site/architecture/safety.md):

- reversible/additive editor edit (UndoRedo)        → ``mutating``
- removal/overwrite of existing data, or an
  irreversible disk/project write                   → ``destructive`` (confirm)
- side-effecting observation (recorder/sampling/
  reimport)                                         → ``runtime``

This pins the class of every tool the audit reclassified, and that the approval
webhook is consulted for the RUNTIME tools that write disk or execute code.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalResponse
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.runtime import RunOutput
from mcp_server.safety import ApprovalGate
from mcp_server.server import create_server
from mcp_server.transforms import _original_handler_name
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# handler fn name -> expected safety_class (issue #638).
EXPECTED_CLASS: dict[str, str] = {
    # irreversible disk/project writes (or removals) → destructive
    "create_resource": "destructive",
    "cross_scene_set_property": "destructive",
    "set_setting": "destructive",
    "register_autoload": "destructive",
    "unregister_autoload": "destructive",
    "disconnect_signal": "destructive",
    "remove_audio_bus": "destructive",
    # side-effecting observations → runtime
    "stop_recording": "runtime",
    "monitor_property": "runtime",
    "rescan_filesystem": "runtime",
    "export_project": "runtime",
    "evaluate_expression": "runtime",
}


async def _registry() -> dict[str, Any]:
    """handler fn name -> registered Tool object (unfiltered)."""
    from mcp_server.bridge import Bridge as _Bridge

    conn = FakeAddonConnection()
    bridge = _Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    tools = await server.local_provider.list_tools()
    return {_original_handler_name(t): t for t in tools}


async def test_listed_tools_have_the_audited_safety_class() -> None:
    registry = await _registry()
    problems: list[str] = []
    for handler, expected in EXPECTED_CLASS.items():
        tool = registry.get(handler)
        if tool is None:
            problems.append(f"{handler}: not registered")
            continue
        actual = (tool.meta or {}).get("safety_class")
        if actual != expected:
            problems.append(f"{handler}: expected {expected}, got {actual}")
    assert not problems, "safety-class audit drift:\n" + "\n".join(problems)


async def test_runtime_write_execute_tools_are_flagged_for_approval() -> None:
    registry = await _registry()
    export = registry["export_project"]
    evaluate = registry["evaluate_expression"]
    assert (export.meta or {}).get("writes_disk"), "export_project must be approval-gated"
    assert (evaluate.meta or {}).get("executes_code"), (
        "evaluate_expression must be approval-gated"
    )


async def test_destructive_tools_expose_confirm() -> None:
    """Every reclassified destructive tool must accept confirm + dry_run."""
    registry = await _registry()
    for handler, expected in EXPECTED_CLASS.items():
        if expected != "destructive":
            continue
        props = (registry[handler].parameters or {}).get("properties", {})
        assert "confirm" in props, f"{handler} missing confirm"
        assert "dry_run" in props, f"{handler} missing dry_run"


# --- approval coverage for runtime write/execute tools ----------------------


class _FakeRunner:
    binary: str | None = "fake-godot"

    def __init__(self) -> None:
        self.exports: list[str] = []

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"], exit_code=0)

    async def check_shader(self, project_dir: str, shader_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        self.exports.append(output_path)
        return RunOutput(command=["fake"], exit_code=0)

    async def run_tests(
        self, project_dir: str, test_dir: str, timeout: float, test_file: str = ""
    ) -> RunOutput:
        return RunOutput(command=["fake"], exit_code=0)


def _deny_gate() -> tuple[ApprovalGate, list[str]]:
    seen: list[str] = []

    async def poster(url: str, request: object, timeout: float) -> ApprovalResponse:
        seen.append(request.action)  # type: ignore[attr-defined]
        return ApprovalResponse(approved=False, reason="denied by reviewer")

    return ApprovalGate(webhook_url="http://hook", poster=poster), seen


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_list_export_presets":
        return ResponseEnvelope.success(
            cmd.id,
            {
                "has_config": True,
                "presets": [
                    {"index": 0, "name": "Linux", "platform": "Linux", "runnable": True,
                     "export_path": ""}
                ],
            },
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


async def test_export_project_is_gated_by_the_approval_webhook() -> None:
    gate, seen = _deny_gate()
    conn = FakeAddonConnection(responder=_responder)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    server = create_server(config, bridge=bridge, runner=_FakeRunner(), approval=gate)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "export"})
        result = await client.call_tool(
            "godot_export_project",
            {"preset": "Linux", "output_path": "build/game.x86_64"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "APPROVAL_DENIED" in str(result.content)
    assert seen == ["godot_export_project"], "the webhook must see the export"


async def test_evaluate_expression_is_gated_by_the_approval_webhook() -> None:
    gate, seen = _deny_gate()
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge, approval=gate)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "debugger"})
        result = await client.call_tool(
            "godot_debugger_evaluate_expression",
            {"expression": "OS.execute('rm -rf /')"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "APPROVAL_DENIED" in str(result.content)
    assert seen == ["godot_debugger_evaluate_expression"]
    assert "cmd_evaluate_expression" not in [
        CommandEnvelope.model_validate_json(s).command for s in conn.sent
    ]


# --- fail-closed default ----------------------------------------------------


async def test_unreachable_webhook_fails_closed_by_default() -> None:
    async def unreachable(url: str, request: object, timeout: float) -> ApprovalResponse:
        raise TimeoutError("webhook down")

    gate = ApprovalGate(webhook_url="http://hook", poster=unreachable)  # default fail_open
    with pytest.raises(Exception) as exc:
        await gate.require(
            action="godot_scene_edit_delete_node", safety_class="destructive", params={}
        )
    assert "APPROVAL_DENIED" in str(exc.value)


def test_config_defaults_to_fail_closed() -> None:
    assert ServerConfig().approval_fail_open is False
    assert ApprovalGate().fail_open is False
