"""Contract tests for ``validate_project`` failure paths (#794).

The feature is covered end-to-end in
``tests/integration/test_validate_project_e2e.py`` (real Godot). These tests pin
the server-side branches that e2e cannot reach cheaply: missing project/runner/
binary, timeout, malformed or absent runner output, and the exact headless
invocation (scope + warning flags). No Godot process is started.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.tools import validation
from tests.fakes import FakeAddonConnection, connector_for


class _FakeProcess:
    """Stands in for the headless Godot subprocess."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", *, delay: float = 0.0):
        self._stdout = stdout
        self._stderr = stderr
        self._delay = delay
        self.returncode = 0
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return 0


def _project(tmp_path: Path, *, runner: bool = True) -> Path:
    if runner:
        runner_path = tmp_path / "addons" / "godot_mcp" / "validation_runner.gd"
        runner_path.parent.mkdir(parents=True)
        runner_path.write_text("# runner stub\n", encoding="utf-8")
    return tmp_path


def _server(project: str) -> FastMCP:
    config = ServerConfig(godot_project_dir=project)
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(config, bridge=bridge)


async def _call(server: FastMCP, **arguments: Any) -> Any:
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "analysis"})
        return await client.call_tool(
            "godot_analysis_validate_project", arguments, raise_on_error=False
        )


def _patch_process(
    monkeypatch: pytest.MonkeyPatch, process: _FakeProcess
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_exec(*args: Any, **_kwargs: Any) -> _FakeProcess:
        captured["args"] = args
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr(validation, "find_godot_binary", lambda _config: "godot-fake")
    return captured


@pytest.mark.asyncio
async def test_missing_project_directory_is_a_precondition(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    result = await _call(_server(str(missing)))

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "project_dir"


@pytest.mark.asyncio
async def test_missing_addon_runner_is_a_precondition(tmp_path: Path) -> None:
    result = await _call(_server(str(_project(tmp_path, runner=False))))

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "addon_installed"


@pytest.mark.asyncio
async def test_missing_godot_binary_is_a_precondition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validation, "find_godot_binary", lambda _config: None)
    result = await _call(_server(str(_project(tmp_path))))

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "godot_bin"


@pytest.mark.asyncio
async def test_timeout_kills_the_process_and_reports_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _FakeProcess(delay=5.0)
    _patch_process(monkeypatch, process)
    monkeypatch.setattr(validation, "_TIMEOUT", 0.05)

    result = await _call(_server(str(_project(tmp_path))))

    assert process.killed is True
    assert result.is_error
    assert result.structured_content["error"] == "TIMEOUT"


@pytest.mark.asyncio
async def test_malformed_runner_payload_is_an_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_process(monkeypatch, _FakeProcess(b"GODOT_MCP_VALIDATION {not-json\n"))

    result = await _call(_server(str(_project(tmp_path))))

    assert result.is_error
    assert result.structured_content["error"] == "INTERNAL_ERROR"
    assert "not JSON" in result.structured_content["hint"]


@pytest.mark.asyncio
async def test_absent_runner_payload_names_the_exit_and_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _FakeProcess(b"just logs\n", b"script crashed\n")
    process.returncode = 1
    _patch_process(monkeypatch, process)

    result = await _call(_server(str(_project(tmp_path))))

    assert result.is_error
    assert result.structured_content["error"] == "INTERNAL_ERROR"
    hint = result.structured_content["hint"]
    assert "exit 1" in hint
    assert "script crashed" in hint


@pytest.mark.asyncio
async def test_happy_path_parses_findings_and_passes_scope_and_warning_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "valid": False,
        "findings": [
            {"severity": "error", "path": "res://x.tscn", "message": "boom"},
        ],
        "validators": ["res://.mcp/validators/custom.gd"],
    }
    stdout = b"scan noise\n" + b"GODOT_MCP_VALIDATION " + json.dumps(payload).encode() + b"\n"
    captured = _patch_process(monkeypatch, _FakeProcess(stdout))
    project = _project(tmp_path)

    result = await _call(
        _server(str(project)),
        include_warnings=True,
        paths=["res://scripts", "res://scripts/"],
    )

    assert result.is_error is False
    assert result.structured_content["valid"] is False
    assert result.structured_content["findings"][0]["message"] == "boom"
    assert result.structured_content["validators"] == ["res://.mcp/validators/custom.gd"]
    assert result.structured_content["project_dir"] == str(project)
    assert result.structured_content["scoped_to"] == ["res://scripts"]  # deduped, slash-stripped
    args = captured["args"]
    assert "--include-warnings" in args
    assert args.count("--scope=res://scripts") == 1
    assert args[0] == "godot-fake"
    assert "--headless" in args
    assert "--script" in args
