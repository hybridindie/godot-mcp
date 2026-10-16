"""Unit tests for the e2e editor-lifecycle helpers (issue #712, deterministic).

These pin the two things the flaky live-editor suite depended on: the listener is
bound *before* the editor is launched (so the ephemeral port can't be stolen in the
gap), and an editor process is always reaped on teardown. Fakes stand in for the
socket/process so there is no real I/O.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from tests.integration._godot import serve_and_launch_editor, stop_editor


class FakeProc:
    """A subprocess.Popen stand-in that records its lifecycle calls."""

    def __init__(
        self,
        *,
        already_exited: bool = False,
        exit_on_terminate: bool = True,
        exit_on_kill: bool = True,
    ) -> None:
        self._rc: int | None = 0 if already_exited else None
        self.calls: list[str] = []
        self._exit_on_terminate = exit_on_terminate
        self._exit_on_kill = exit_on_kill

    def poll(self) -> int | None:
        return self._rc

    def terminate(self) -> None:
        self.calls.append("terminate")
        if self._exit_on_terminate:
            self._rc = 0

    def kill(self) -> None:
        self.calls.append("kill")
        if self._exit_on_kill:
            self._rc = 1

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if self._rc is None:
            raise subprocess.TimeoutExpired(
                cmd="godot", timeout=timeout if timeout is not None else 0.0
            )
        return self._rc


def test_stop_editor_noop_when_already_exited() -> None:
    proc = FakeProc(already_exited=True)
    stop_editor(proc)  # type: ignore[arg-type]
    assert proc.calls == []


def test_stop_editor_terminates_and_waits() -> None:
    proc = FakeProc(exit_on_terminate=True)
    stop_editor(proc)  # type: ignore[arg-type]
    assert proc.calls == ["terminate", "wait"]


def test_stop_editor_kills_when_terminate_times_out() -> None:
    proc = FakeProc(exit_on_terminate=False, exit_on_kill=True)
    stop_editor(proc)  # type: ignore[arg-type]
    # terminate → wait (times out) → kill → wait (reaped) — never left lingering.
    assert proc.calls == ["terminate", "wait", "kill", "wait"]


class FakeBridge:
    def __init__(self, order: list[str], *, connected: bool) -> None:
        self._order = order
        self.connected = connected

    async def serve(self) -> None:
        self._order.append("serve")


@pytest.mark.asyncio
async def test_serve_binds_before_launching_the_editor() -> None:
    order: list[str] = []
    bridge = FakeBridge(order, connected=True)

    def launch() -> Any:
        order.append("launch")
        return FakeProc()

    proc = await serve_and_launch_editor(bridge, launch, timeout=1)
    assert order == ["serve", "launch"]  # the port is claimed before the editor dials it
    assert isinstance(proc, FakeProc)


@pytest.mark.asyncio
async def test_never_connected_stops_the_editor_and_raises() -> None:
    order: list[str] = []
    bridge = FakeBridge(order, connected=False)
    proc = FakeProc(exit_on_terminate=True)

    def launch() -> Any:
        return proc

    with pytest.raises(AssertionError, match="never connected"):
        # timeout=0 → wait_until gives up on the first check, no real sleeping.
        await serve_and_launch_editor(bridge, launch, timeout=0)
    assert order == ["serve"]
    assert proc.calls == ["terminate", "wait"]  # the launched editor is not leaked
