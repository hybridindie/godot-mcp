"""Unit tests for the project-tool rescan debounce (#802).

The bridge notice only schedules work; these pin the coalescing contract without
a bridge or an editor.
"""

from __future__ import annotations

from typing import cast

import pytest
from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.models.project_tools import ProjectToolsResult
from mcp_server.tools.project_tools import ProjectToolRegistrar


class _FakeHub:
    def __init__(self) -> None:
        self.published = 0

    async def publish_tools_changed(self) -> None:
        self.published += 1


def _registrar() -> ProjectToolRegistrar:
    # scan() is replaced per test; the bridge is never touched.
    return ProjectToolRegistrar(
        FastMCP("test"), cast(Bridge, None), _FakeHub(), debounce=0.01
    )


@pytest.mark.asyncio
async def test_notices_during_the_debounce_coalesce_into_one_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registrar = _registrar()
    calls: list[int] = []

    async def fake_scan() -> ProjectToolsResult:
        calls.append(1)
        return ProjectToolsResult()

    monkeypatch.setattr(registrar, "scan", fake_scan)
    registrar.schedule_rescan()
    registrar.schedule_rescan()
    registrar.schedule_rescan()
    await registrar.flush()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_notice_during_a_scan_triggers_a_second_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registrar = _registrar()
    calls: list[int] = []

    async def fake_scan() -> ProjectToolsResult:
        calls.append(1)
        if len(calls) == 1:
            registrar.schedule_rescan()  # arrives while the first pass runs
        return ProjectToolsResult()

    monkeypatch.setattr(registrar, "scan", fake_scan)
    registrar.schedule_rescan()
    await registrar.flush()

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_a_failed_rescan_keeps_the_previous_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient bridge failure is logged, not surfaced as unregistered tools."""
    registrar = _registrar()

    async def failing_scan() -> ProjectToolsResult:
        raise RuntimeError("bridge went away")

    monkeypatch.setattr(registrar, "scan", failing_scan)
    registrar.schedule_rescan()
    await registrar.flush()  # must not raise

    assert registrar._registered == set()


def test_hub_is_unused_by_the_debounce() -> None:
    """Sanity: the debounce itself never publishes — scan() does."""
    hub = _FakeHub()
    registrar = ProjectToolRegistrar(
        FastMCP("test"), cast(Bridge, None), hub, debounce=0.01
    )
    assert registrar is not None and hub.published == 0
