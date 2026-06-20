"""Contract tests for export tools (issue #50)."""

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

_PRESETS = {
    "has_config": True,
    "presets": [
        {
            "index": 0,
            "name": "Linux",
            "platform": "Linux",
            "runnable": True,
            "export_path": "build/game.x86_64",
        },
        {"index": 1, "name": "Web", "platform": "Web", "runnable": False, "export_path": ""},
    ],
}


class FakeRunner:
    def __init__(self, output: RunOutput, binary: str | None = "fake-godot") -> None:
        self.binary = binary
        self._output = output
        self.exports: list[tuple[str, str, str, bool]] = []

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return self._output

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return self._output

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        self.exports.append((project_dir, preset, output_path, debug))
        return self._output

    async def run_tests(self, project_dir: str, test_dir: str, timeout: float) -> RunOutput:
        return self._output


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    match cmd.command:
        case "cmd_list_export_presets":
            return ResponseEnvelope.success(cmd.id, _PRESETS)
        case "cmd_get_export_info":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "has_config": True,
                    "preset_count": 2,
                    "preset_names": ["Linux", "Web"],
                    "config_path": "res://export_presets.cfg",
                },
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build(runner: FakeRunner) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge, runner=runner), conn


async def test_gated_with_safety_classes() -> None:
    server, _ = _build(FakeRunner(RunOutput(command=["fake"])))
    async with Client(server) as client:
        assert "export_project" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "export"})
        tools = {t.name: t for t in await client.list_tools()}
    assert {"list_export_presets", "get_export_info", "export_project"} <= set(tools)
    assert tools["list_export_presets"].meta["safety_class"] == "read_only"
    assert tools["get_export_info"].meta["safety_class"] == "read_only"
    assert tools["export_project"].meta["safety_class"] == "runtime"


async def test_list_presets_and_info() -> None:
    server, _ = _build(FakeRunner(RunOutput(command=["fake"])))
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "export"})
        presets = await client.call_tool("list_export_presets", {})
        info = await client.call_tool("get_export_info", {})
    assert presets.structured_content["presets"][0]["name"] == "Linux"
    assert info.structured_content["preset_names"] == ["Linux", "Web"]


async def test_export_project_runs_known_preset() -> None:
    runner = FakeRunner(RunOutput(command=["godot", "--export-release"], stdout="ok", exit_code=0))
    server, _ = _build(runner)
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "export"})
        result = await client.call_tool(
            "export_project", {"preset": "Linux", "output_path": "build/game.x86_64"}
        )
    sc = result.structured_content
    assert sc["exported"] is True and sc["exit_code"] == 0
    assert sc["preset"] == "Linux" and sc["output_path"] == "build/game.x86_64"
    assert runner.exports == [("/tmp/proj", "Linux", "build/game.x86_64", False)]


async def test_export_project_rejects_unknown_preset() -> None:
    server, _ = _build(FakeRunner(RunOutput(command=["fake"])))
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "export"})
        result = await client.call_tool(
            "export_project", {"preset": "Nope", "output_path": "x"}, raise_on_error=False
        )
    assert result.is_error and "Nope" in str(result.content)


async def test_export_project_requires_binary() -> None:
    server, _ = _build(FakeRunner(RunOutput(command=["fake"]), binary=None))
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "export"})
        result = await client.call_tool(
            "export_project", {"preset": "Linux", "output_path": "x"}, raise_on_error=False
        )
    assert result.is_error and "godot_bin" in str(result.content)
