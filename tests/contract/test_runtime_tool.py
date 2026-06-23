"""Contract tests for the run_and_capture tool (issue #13).

Uses an injected fake Runner so no real Godot is needed.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


class FakeRunner:
    """A Runner double that records its call and returns a canned RunOutput."""

    def __init__(self, output: RunOutput, binary: str | None = "fake-godot") -> None:
        self.binary = binary
        self._output = output
        self.calls: list[tuple[str, str | None, float]] = []

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        self.calls.append((project_dir, scene, timeout))
        return self._output

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return self._output

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        self.calls.append((project_dir, f"{preset}->{output_path}", timeout))
        return self._output

    async def run_tests(self, project_dir: str, test_dir: str, timeout: float) -> RunOutput:
        return self._output


def _build(
    runner: FakeRunner, *, project_dir: str | None = "/tmp/proj"
) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection()
    config = ServerConfig(godot_project_dir=project_dir)
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge, runner=runner), conn


async def _enable_runtime(client: Client) -> None:  # type: ignore[type-arg]
    await client.call_tool("godot_enable_toolset", {"category": "runtime"})


async def test_runtime_tool_is_gated_off_by_default() -> None:
    runner = FakeRunner(RunOutput(command=["fake"]))
    server, _ = _build(runner)
    async with Client(server) as client:
        assert "godot_runtime_run_and_capture" not in {t.name for t in await client.list_tools()}
        await _enable_runtime(client)
        assert "godot_runtime_run_and_capture" in {t.name for t in await client.list_tools()}


async def test_run_and_capture_summarizes_output() -> None:
    output = RunOutput(
        command=["fake", "--headless"],
        stdout="Booting\nRUNTIME_PROBE_OK\nERROR: bad at res://x.gd:7",
        exit_code=0,
    )
    runner = FakeRunner(output)
    server, _ = _build(runner)
    async with Client(server) as client:
        await _enable_runtime(client)
        result = await client.call_tool(
            "godot_runtime_run_and_capture", {"scene": "res://main.tscn"}
        )
    payload = result.structured_content
    assert payload["ran"] is True
    assert payload["exit_code"] == 0
    assert len(payload["errors"]) == 1
    assert "RUNTIME_PROBE_OK" in payload["output"]
    # Project dir from config, scene passed through.
    assert runner.calls[0][0] == "/tmp/proj"
    assert runner.calls[0][1] == "res://main.tscn"


async def test_run_and_capture_is_runtime_safety_class() -> None:
    runner = FakeRunner(RunOutput(command=["fake"]))
    server, _ = _build(runner)
    async with Client(server) as client:
        await _enable_runtime(client)
        tool = next(
            t for t in await client.list_tools() if t.name == "godot_runtime_run_and_capture"
        )
    assert tool.meta is not None and tool.meta.get("safety_class") == "runtime"


async def test_missing_binary_is_structured_error() -> None:
    runner = FakeRunner(RunOutput(command=["fake"]), binary=None)
    server, _ = _build(runner)
    async with Client(server) as client:
        await _enable_runtime(client)
        result = await client.call_tool("godot_runtime_run_and_capture", {}, raise_on_error=False)
    assert result.is_error
    content = str(result.content)
    assert "Godot binary not found" in content
    assert "required=godot_bin" in content  # structured precondition hint


async def test_project_dir_resolved_from_bridge_when_unset() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        if cmd.command == "cmd_get_project_info":
            return ResponseEnvelope.success(cmd.id, {"project_path": "/editor/proj"})
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    runner = FakeRunner(RunOutput(command=["fake"], stdout="ok", exit_code=0))
    conn = FakeAddonConnection(responder=responder)
    config = ServerConfig(godot_project_dir=None)  # force bridge resolution
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    server = create_server(config, bridge=bridge, runner=runner)
    async with Client(server) as client:
        await _enable_runtime(client)
        await client.call_tool("godot_runtime_run_and_capture", {})
    assert runner.calls[0][0] == "/editor/proj"
