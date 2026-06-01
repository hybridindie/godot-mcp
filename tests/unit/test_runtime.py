"""Unit tests for the runtime loop parser and binary discovery (issue #13)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcp_server.config import ServerConfig
from mcp_server.runtime import RunOutput, find_godot_binary, summarize_run


def test_summarize_classifies_errors_warnings_output() -> None:
    stdout = "\n".join(
        [
            "Godot Engine v4.6.3.stable - https://godotengine.org",
            "RUNTIME_PROBE_OK",
            "SCRIPT ERROR: Invalid call. at: res://player.gd:42",
            "WARNING: deprecated thing used",
        ]
    )
    result = summarize_run(RunOutput(command=["godot"], stdout=stdout, exit_code=0))

    assert result.ran is True
    assert result.exit_code == 0
    assert len(result.errors) == 1
    assert result.errors[0].type == "error"
    assert result.errors[0].source == "res://player.gd"
    assert result.errors[0].line == 42
    assert len(result.warnings) == 1
    assert "RUNTIME_PROBE_OK" in result.output


def test_summarize_merges_stdout_and_stderr() -> None:
    out = RunOutput(command=["godot"], stdout="hello", stderr="ERROR: boom", exit_code=1)
    result = summarize_run(out)
    assert "hello" in result.output
    assert len(result.errors) == 1


def test_summarize_marks_timeout() -> None:
    out = RunOutput(command=["godot"], stdout="", timed_out=True, exit_code=None)
    result = summarize_run(out)
    assert result.timed_out is True
    assert result.exit_code is None


def test_find_godot_binary_uses_config() -> None:
    config = ServerConfig(godot_bin=sys.executable)  # any real file
    assert find_godot_binary(config) == sys.executable


def test_find_godot_binary_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.runtime.shutil.which", lambda name: "/usr/bin/godot")
    monkeypatch.setattr("mcp_server.runtime._MAC_APP", Path("/does/not/exist"))
    assert find_godot_binary(ServerConfig()) == "/usr/bin/godot"


def test_find_godot_binary_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.runtime.shutil.which", lambda name: None)
    monkeypatch.setattr("mcp_server.runtime._MAC_APP", Path("/does/not/exist"))
    assert find_godot_binary(ServerConfig()) is None
