"""Contract tests for the run_tests tool (issue #206).

In-memory client + fake addon peer + injected fake runner. Verifies the tool
runs the suite and returns structured results, and that a missing GUT install is
a normal ``framework_absent`` outcome (not an error) without launching Godot.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

_GUT_FAIL = """\
res://test/test_enemy.gd
  test_spawns
    [Failed]:  Expected [3] to equal [2]
        at line 14
Totals
Passing tests      2
Failing tests      1
---- 1 of 3 tests failed (3 ran). ----
"""


class _FakeRunner:
    binary: str | None = "fake-godot"

    def __init__(self, output: RunOutput) -> None:
        self._output = output
        self.run_tests_calls: list[tuple[str, str]] = []

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        return RunOutput(command=["fake"])

    async def run_tests(self, project_dir: str, test_dir: str, timeout: float) -> RunOutput:
        self.run_tests_calls.append((project_dir, test_dir))
        return self._output


def _build(project_dir: str, output: RunOutput) -> tuple[FastMCP, _FakeRunner]:
    config = ServerConfig(godot_project_dir=project_dir)
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    runner = _FakeRunner(output)
    return create_server(config, bridge=bridge, runner=runner), runner


def _with_gut(project_dir: Path) -> None:
    gut = project_dir / "addons" / "gut"
    gut.mkdir(parents=True, exist_ok=True)
    (gut / "gut_cmdln.gd").write_text("# gut runner stub\n")


async def test_run_tests_returns_structured_results(tmp_path: Path) -> None:
    _with_gut(tmp_path)
    output = RunOutput(command=["gut"], stdout=_GUT_FAIL, exit_code=1)
    server, runner = _build(str(tmp_path), output)
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "testing"})
        result = await client.call_tool("run_tests", {"test_dir": "res://test"})
    data = result.data
    assert data.ran is True and data.framework == "gut" and data.framework_absent is False
    assert data.passed == 2 and data.failed == 1 and data.total == 3
    assert data.exit_code == 1
    assert any("Expected [3] to equal [2]" in f.message for f in data.failures)
    assert runner.run_tests_calls == [(str(tmp_path), "res://test")]


async def test_run_tests_reports_framework_absent_without_launching(tmp_path: Path) -> None:
    # No addons/gut/ in the project.
    server, runner = _build(str(tmp_path), RunOutput(command=["gut"], stdout=_GUT_FAIL))
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "testing"})
        result = await client.call_tool("run_tests", {})
    data = result.data
    assert data.framework_absent is True and data.ran is False
    assert runner.run_tests_calls == []  # never launched Godot


async def test_run_tests_in_testing_toolset(tmp_path: Path) -> None:
    server, _ = _build(str(tmp_path), RunOutput(command=["gut"]))
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "testing"})
        names = {t.name for t in await client.list_tools()}
    assert "run_tests" in names
