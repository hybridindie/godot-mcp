"""Contract tests for bridge/runtime lifecycle cleanups (issue #655).

- cancelling a run kills the headless subprocess (no orphaned Godot);
- bridge `close()` cancels AND awaits the reader;
- a bind failure is retried and surfaced in `godot_health_check`.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.runtime import GodotRunner
from mcp_server.tools.health import build_health

_REPO = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (_REPO / rel).read_text(encoding="utf-8")


def test_exec_reaps_the_subprocess_on_cancel() -> None:
    src = _src("mcp_server/runtime.py")
    body = src.split("async def _exec", 1)[1]
    assert "except asyncio.CancelledError" in body
    assert "proc.kill()" in body


async def test_exec_propagates_cancellation() -> None:
    """A cancel must re-raise (not be swallowed) after reaping the child."""
    runner = GodotRunner(ServerConfig(godot_bin="/bin/true"))
    task = asyncio.ensure_future(runner._exec(["sleep", "30"], timeout=30.0))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_bridge_close_cancels_and_awaits_the_reader() -> None:
    src = inspect.getsource(Bridge.close)
    assert "await reader" in src, "close() must await the cancelled reader (#655)"


def test_bind_failure_is_retried_and_surfaced() -> None:
    assert "bind_error" in _src("mcp_server/bridge.py")
    server = _src("mcp_server/server.py")
    assert "bridge.bind_error" in server and "for attempt in range" in server
    assert "bridge_bind_error=bridge.bind_error" in _src("mcp_server/tools/health.py")


def test_health_reports_a_bind_error() -> None:
    bridge = Bridge(BridgeConfig())
    bridge.bind_error = "address already in use"
    status = build_health(bridge, ServerConfig())
    assert status.bridge_bind_error == "address already in use"
