"""Unit tests for the extracted debug-workflow service (issue #176).

`build_report` is the pure report-assembly function pulled out of the old
159-line `debug_workflow` tool body; `run_debug_workflow` is the orchestrator.
These pin the report wording/ordering so the refactor preserves behavior.
"""

from __future__ import annotations

import asyncio

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.debug_workflow import build_report, run_debug_workflow
from mcp_server.models.runtime import LogEntry, RunCaptureResult
from mcp_server.models.scripts import ParseError
from mcp_server.runtime import GodotRunner
from tests.fakes import FakeAddonConnection, connector_for

HEALTHY = "No obvious issues detected. The project appears healthy."


def _run(errors: list[LogEntry] | None = None, **kw: object) -> RunCaptureResult:
    base: dict[str, object] = dict(
        ran=True, exit_code=0, timed_out=False, duration_seconds=0.1,
        errors=errors or [], warnings=[], output=[], command=["fake"],
    )
    base.update(kw)
    return RunCaptureResult(**base)  # type: ignore[arg-type]


def test_build_report_healthy_project() -> None:
    findings, suggestions = build_report(
        bridge_connected=True, tree_result={"tree": {"name": "Root"}},
        run_result=_run(), run_skipped=None, parse_errors=[], parse_skipped=None,
    )
    assert findings == [HEALTHY]
    assert suggestions == ["Consider running run_test_scenario() for deeper play-testing."]


def test_build_report_disconnected_no_scene_parse_skipped() -> None:
    findings, _ = build_report(
        bridge_connected=False, tree_result=None, run_result=None,
        run_skipped=None, parse_errors=[], parse_skipped="no binary",
    )
    assert any(f.startswith("BRIDGE DISCONNECTED") for f in findings)
    assert any(f.startswith("NO ACTIVE SCENE") for f in findings)
    assert "PARSE CHECK SKIPPED: no binary" in findings
    assert HEALTHY not in findings


def test_build_report_run_errors_warnings_timeout() -> None:
    run = _run(
        errors=[LogEntry(type="error", message="boom", source="res://x.gd", line=5)],
        warnings=[LogEntry(type="warning", message="meh", source=None, line=None)],
        timed_out=True, exit_code=None,
    )
    findings, suggestions = build_report(
        bridge_connected=True, tree_result={"tree": {}}, run_result=run,
        run_skipped=None, parse_errors=[], parse_skipped=None,
    )
    assert any(f.startswith("RUNTIME ERRORS") for f in findings)
    assert any(f.startswith("RUNTIME WARNINGS") for f in findings)
    assert any(f.startswith("RUN TIMED OUT") for f in findings)
    assert any(f.startswith("NON-ZERO EXIT") for f in findings)  # exit_code None != 0
    assert "  [ERROR] boom at res://x.gd:5" in suggestions


def test_build_report_run_skipped_is_first_finding() -> None:
    findings, _ = build_report(
        bridge_connected=False, tree_result={"tree": {}}, run_result=None,
        run_skipped="cannot resolve project dir", parse_errors=[], parse_skipped=None,
    )
    assert findings[0] == "HEADLESS RUN SKIPPED: cannot resolve project dir"


def test_build_report_parse_errors_take_precedence_over_skipped() -> None:
    findings, _ = build_report(
        bridge_connected=True, tree_result={"tree": {}}, run_result=_run(),
        run_skipped=None,
        parse_errors=[ParseError(message="bad", source="res://a.gd", line=1)],
        parse_skipped="should be ignored",
    )
    assert any(f.startswith("PARSE ERRORS") for f in findings)
    assert not any("PARSE CHECK SKIPPED" in f for f in findings)


def test_run_debug_workflow_orchestrates_to_model() -> None:
    async def go() -> None:
        bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection()))
        await bridge.connect()
        runner = GodotRunner(ServerConfig())
        runner.binary = None  # force "no Godot" path → parse/run skipped, deterministic
        result = await run_debug_workflow(bridge, ServerConfig(), runner, "", 5.0)
        assert result.bridge["connected"] is True
        assert result.scene_tree is None
        assert result.run is None
        assert result.parse["skipped_reason"] is not None
        assert any(f.startswith("NO ACTIVE SCENE") for f in result.findings)
        await bridge.close()

    asyncio.run(go())
