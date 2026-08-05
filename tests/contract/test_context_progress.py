"""Contract test: long-running tools stream progress + logs via Context (issue #223).

run_tests / run_and_capture / export_project are multi-second operations. They must
accept a FastMCP ``Context`` and emit progress updates and structured log messages so
the client/agent has observability during the slow call.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client, FastMCP
from mcp.types import LoggingMessageNotificationParams

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

_GUT_PASS = """\
Totals
Passing tests      3
Failing tests      0
---- 3 of 3 tests passed (3 ran). ----
"""


class _FakeRunner:
    binary: str | None = "fake-godot"

    def __init__(self, output: RunOutput) -> None:
        self._output = output

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return self._output

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        return self._output

    async def run_tests(self, project_dir: str, test_dir: str, timeout: float) -> RunOutput:
        return self._output


def _build(project_dir: str, output: RunOutput) -> FastMCP:
    config = ServerConfig(godot_project_dir=project_dir)
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(config, bridge=bridge, runner=_FakeRunner(output))


def _with_gut(project_dir: Path) -> None:
    gut = project_dir / "addons" / "gut"
    gut.mkdir(parents=True, exist_ok=True)
    (gut / "gut_cmdln.gd").write_text("# gut runner stub\n")


async def test_run_tests_streams_progress_and_logs(tmp_path: Path) -> None:
    _with_gut(tmp_path)
    server = _build(str(tmp_path), RunOutput(command=["gut"], stdout=_GUT_PASS, exit_code=0))

    progress: list[tuple[float, float | None]] = []
    logs: list[str] = []

    async def on_progress(p: float, total: float | None, message: str | None) -> None:
        progress.append((p, total))

    async def on_log(params: LoggingMessageNotificationParams) -> None:
        logs.append(str(params.data))

    async with Client(server, progress_handler=on_progress, log_handler=on_log) as client:
        await client.call_tool("godot_enable_toolset", {"category": "testing"})
        await client.call_tool("godot_testing_run_tests", {"test_dir": "res://test"})

    assert progress, "expected at least one progress update from run_tests"
    assert logs, "expected at least one structured log message from run_tests"


async def test_safe_progress_noops_on_session_unavailable() -> None:
    """The guarded progress helpers swallow RuntimeError (detached task session).

    Simulates the ``task=True`` detached-session failure by passing a Context
    whose ``info``/``report_progress`` raise ``RuntimeError: session is not
    available``. The tools must complete successfully — the progress calls
    no-op instead of propagating the error.
    """
    from mcp_server.tools._progress import safe_info, safe_progress

    class _BrokenCtx:
        async def info(self, msg: str, *args: object, **kwargs: object) -> None:
            raise RuntimeError("session is not available")

        async def report_progress(
            self, current: float, total: float, *args: object, **kwargs: object
        ) -> None:
            raise RuntimeError("session is not available")

    ctx = _BrokenCtx()
    await safe_info(ctx, "should not raise")
    await safe_progress(ctx, 0, 1)
    await safe_progress(ctx, 1, 1)
