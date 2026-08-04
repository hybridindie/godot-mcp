"""Contract tests for the FastMCP 4.0 background-tasks spike (issue #315).

Spike scope: verify that a background task awaiting a bridge operation does not
race with a concurrent MCP request that touches the same single-active-peer
bridge, and surface what the 4.0b1 API shape actually is.

Findings encoded here (the PR body mirrors these):
  * The TasksExtension installs cleanly via ``fastmcp[tasks]==4.0.0b1`` +
    ``constraint-dependencies = ["fastmcp-tasks==4.0.0b1"]``. The upgrade-guide
    suggestion to also pin ``mcp==2.0.0b2`` / ``mcp-types==2.0.0b2`` is
    *unsatisfiable*: fastmcp-slim 4.0.0b1 declares ``mcp-types>=2.0.0`` (final),
    which excludes the 2.0.0b2 prerelease. The final 2.0.0 versions already in
    the graph are correct; only ``fastmcp-tasks`` needs the prerelease pin.
  * The 4.0b1 server API: ``mcp.add_extension(TasksExtension())`` then
    ``@mcp.tool(task=True)``. The client API: ``import fastmcp_tasks`` (enables
    client-side task support) then ``call_tool_task(client, name, args)`` ->
    ``ToolTask`` with ``.task_id``, ``.status()``, ``.result()``, ``.wait()``,
    ``.cancel()``. A task tool carries ``tool.task_config.mode == 'optional'``;
    a normal tool is ``'forbidden'``.
  * Concurrent bridge access is SAFE: the bridge's per-``id`` future map means
    multiple in-flight ``send()`` calls on the same active peer resolve
    independently via the shared read loop. The ``_attach_lock`` only serialises
    *peer swap*, not sends, so a background task awaiting a bridge response does
    not block or race a concurrent ``send``. This is the spike's main answer.
  * LIMITATION (the blocker): a tool body that uses ``ctx.info`` /
    ``ctx.report_progress`` (as ``run_and_capture``, ``run_tests``,
    ``export_project`` and ``bake_navigation_mesh`` all do) CANNOT run as a
    background task as-is. ``task=True`` is not opt-in per call — it routes
    *every* invocation (plain ``call_tool`` included) through the task input
    loop, which runs detached from the MCP request session, so ``ctx.session``
    is ``None`` and ``ctx.info`` raises ``RuntimeError: session is not
    available``. Adopting ``task=True`` for those four tools requires first
    refactoring them to drop or guard the ctx-progress calls. The spike
    therefore leaves them all un-tasked and documents the finding.
"""

from __future__ import annotations

import asyncio

import fastmcp_tasks  # noqa: F401  — enables Client-side task support
import pytest
from fastmcp import Client, Context, FastMCP
from fastmcp_tasks import TasksExtension, call_tool_task

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

TASKS_EXT_KEY = "io.modelcontextprotocol/tasks"


class SlowRunner:
    """A Runner double whose ``run`` awaits ``delay`` before returning, so the
    tool call is genuinely in-flight (and the MCP request held open) for a
    measurable window — the condition the spike wants to background."""

    def __init__(self, output: RunOutput, delay: float, binary: str | None = "fake-godot") -> None:
        self.binary = binary
        self._output = output
        self._delay = delay
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        self.started.set()
        await asyncio.sleep(self._delay)
        self.finished.set()
        return self._output

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return self._output

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        return self._output

    async def run_tests(self, project_dir: str, test_dir: str, timeout: float) -> RunOutput:
        return self._output


async def test_tasks_extension_is_registered_on_the_server() -> None:
    """``create_server`` registers the TasksExtension (spike artifact) so the
    server is ready to host ``task=True`` tools once a tool is refactored to be
    task-safe. No tool is currently marked ``task=True`` — see the reproducers
    below for why."""
    server = create_server()
    extensions = server._extensions
    assert TASKS_EXT_KEY in extensions
    assert isinstance(extensions[TASKS_EXT_KEY], TasksExtension)


async def test_run_and_capture_is_not_marked_task_to_avoid_ctx_session_breakage() -> None:
    """The spike reverted ``task=True`` on ``run_and_capture``: marking it
    task-capable routes *all* calls (not just ``call_tool_task``) through the
    task input loop, which runs detached from the MCP session — so the tool
    body's ``ctx.info`` / ``ctx.report_progress`` raise ``session is not
    available``. ``task_config.mode`` is therefore ``'forbidden'`` (the default),
    confirming the revert. See ``test_ctx_progress_in_task_body_raises`` for the
    reproducer of the underlying mechanism."""
    runner = SlowRunner(RunOutput(command=["fake"]), delay=0.01)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    server = create_server(config, bridge=bridge, runner=runner)
    # The runtime toolset is gated off by default; enable it so the tool is
    # registered (and thus introspectable via get_tool).
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
    tool = await server.get_tool("godot_runtime_run_and_capture")
    assert tool is not None
    assert tool.task_config is not None
    assert tool.task_config.mode == "forbidden"


async def test_ctx_free_task_runs_as_background_task_and_polls_to_result() -> None:
    """Control case: a task-enabled tool that does NOT touch ``ctx`` runs as a
    background task — ``call_tool_task`` returns a handle immediately and
    ``task.result()`` resolves to the structured output. This confirms the
    TasksExtension + 4.0b1 API works end-to-end in-process; the reason
    ``run_and_capture`` itself isn't task-enabled is the ctx-session reproducer
    below, not a problem with the tasks machinery."""
    server = FastMCP("control")
    server.add_extension(TasksExtension())

    @server.tool(task=True)
    async def double(x: int) -> int:
        await asyncio.sleep(0.02)
        return x * 2

    async with Client(server) as client:
        task = await call_tool_task(client, "double", {"x": 21})
        assert task.task_id  # a real handle, not None
        result = await task.result()
    assert result.is_error is False
    assert result.structured_content == {"result": 42}


async def test_concurrent_bridge_access_works_while_background_task_in_flight() -> None:
    """The spike's central question: while a background task is awaiting a slow
    bridge operation, can a second concurrent ``bridge.send`` proceed and complete
    correctly on the same single-active-peer bridge?

    Answer: YES. The bridge's per-``id`` future map means concurrent in-flight
    sends resolve independently via the shared read loop; the ``_attach_lock``
    only serialises peer *swap*, not sends. A background task awaiting a bridge
    response does not block or race a concurrent send on the same active peer.

    This uses a ctx-free task tool so the mechanism is exercised (a real bridge
    send in flight) without the ctx.session failure short-circuiting the probe.
    """
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
    server = FastMCP("probe")
    server.add_extension(TasksExtension())

    in_flight = asyncio.Event()

    @server.tool(task=True)
    async def slow_bridge_op() -> str:
        # A real bridge.send on the shared bridge — the exact pattern
        # bake/export/run_tests use, awaited while we fire concurrent sends.
        in_flight.set()
        env = await bridge.send("cmd_get_project_info")
        return f"task:{env.ok}"

    await bridge.serve()
    async with Client(server) as client:
        task = await call_tool_task(client, "slow_bridge_op", {})
        await asyncio.wait_for(in_flight.wait(), timeout=1.0)
        # While the task's bridge.send is in flight, fire two concurrent direct
        # sends on the SAME bridge the task is using.
        ping_p, info_p = await asyncio.gather(
            bridge.send("cmd_ping"),
            bridge.send("cmd_get_project_info"),
        )
        assert ping_p.ok and ping_p.result == {"pong": True}
        assert info_p.ok
        assert info_p.result is not None
        assert info_p.result["project_path"] == "/tmp/test_project"
        result = await task.result()
    assert result.is_error is False
    assert result.structured_content == {"result": "task:True"}


async def test_ctx_progress_in_task_body_raises_session_unavailable() -> None:
    """Spike finding reproducer: a task-enabled tool whose body calls
    ``ctx.info`` / ``ctx.report_progress`` raises at runtime because the
    detached background task runs outside the MCP request session
    (``ctx.session`` is ``None``). Marking such a tool ``task=True`` routes
    *all* calls (not just ``call_tool_task``) through the task input loop, so
    even a plain ``call_tool`` breaks the same way — this is why the spike
    reverted ``task=True`` on ``run_and_capture``, ``run_tests``,
    ``export_project`` and ``bake_navigation_mesh`` (all use ctx progress).
    Adopting background tasks for them requires first refactoring away the
    ctx-progress calls or guarding them for the task path.
    """
    server = FastMCP("ctx-probe")
    server.add_extension(TasksExtension())

    @server.tool(task=True)
    async def uses_ctx_progress(x: int, *, ctx: Context) -> int:
        # Mirrors run_and_capture's `await ctx.info(...)` / `ctx.report_progress`.
        await ctx.info("working")  # raises: session is not available
        return x

    async with Client(server) as client:
        task = await call_tool_task(client, "uses_ctx_progress", {"x": 1}, raise_on_error=False)
        result = await task.result()
    assert result.is_error is True
    content = str(result.content)
    assert "session is not available" in content or "session has not been established" in content


async def test_ctx_progress_task_also_breaks_plain_call_tool() -> None:
    """The decisive spike finding: ``task=True`` is not opt-in per call. It routes
    *every* invocation (plain ``call_tool`` included) through the task input loop,
    so the ctx-session failure isn't limited to ``call_tool_task`` — the tool is
    broken for normal callers too. This is why the spike reverts ``task=True``
    rather than leaving it on with a "use call_tool, not call_tool_task" caveat."""
    server = FastMCP("ctx-probe2")
    server.add_extension(TasksExtension())

    @server.tool(task=True)
    async def uses_ctx_progress2(x: int, *, ctx: Context) -> int:
        await ctx.info("working")
        return x

    async with Client(server) as client:
        result = await client.call_tool("uses_ctx_progress2", {"x": 1}, raise_on_error=False)
    assert result.is_error
    content = str(result.content)
    assert "session is not available" in content or "session has not been established" in content