"""Unit: the config generator merges client configs without clobbering (#762)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from mcp_server import cli


def test_claude_code_print_and_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "game"
    project.mkdir()
    assert cli.main(["config", "--client", "claude-code", "--project", str(project)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mcpServers"]["godot-mcp"]["command"] == "uvx"
    assert printed["mcpServers"]["godot-mcp"]["env"]["GODOT_MCP_PROJECT_DIR"] == str(project)

    assert (
        cli.main(
            ["config", "--client", "claude-code", "--project", str(project), "--write"]
        )
        == 0
    )
    target = project / ".mcp.json"
    assert json.loads(target.read_text())["mcpServers"]["godot-mcp"]["args"] == [
        "godot-editor-mcp"
    ]
    with pytest.raises(SystemExit, match="already has"):
        cli.main(["config", "--client", "claude-code", "--project", str(project), "--write"])
    assert cli.main(
        ["config", "--client", "claude-code", "--project", str(project), "--write", "--force"]
    ) == 0


def test_cursor_and_vscode_merge_other_servers(tmp_path: Path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    cursor = project / ".cursor" / "mcp.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    assert cli.main(["config", "--client", "cursor", "--project", str(project), "--write"]) == 0
    merged = json.loads(cursor.read_text())
    assert set(merged["mcpServers"]) == {"other", "godot-mcp"}

    vscode = project / ".vscode" / "mcp.json"
    assert cli.main(["config", "--client", "vscode", "--project", str(project), "--write"]) == 0
    entries = json.loads(vscode.read_text())["servers"]
    assert entries["godot-mcp"]["type"] == "stdio"


def test_codex_toml_append_force_and_preserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text("[other]\nvalue = 1\n")
    project = tmp_path / "game"
    project.mkdir()
    assert cli.main(["config", "--client", "codex", "--project", str(project), "--write"]) == 0
    text = cfg.read_text()
    assert "[other]\nvalue = 1" in text
    assert "[mcp_servers.godot-mcp]" in text
    assert text.count("[mcp_servers.godot-mcp]") == 1

    with pytest.raises(SystemExit, match="already has"):
        cli.main(["config", "--client", "codex", "--project", str(project), "--write"])
    assert cli.main(
        ["config", "--client", "codex", "--project", str(project), "--write", "--force"]
    ) == 0
    assert cfg.read_text().count("[mcp_servers.godot-mcp]") == 1
    capsys.readouterr()


def test_codex_toml_escapes_the_project_path(tmp_path: Path) -> None:
    project = tmp_path / 'a"b\\c'
    snippet = cli._toml_snippet(project)
    parsed = tomllib.loads(snippet)
    assert parsed["mcp_servers"]["godot-mcp"]["env"]["GODOT_MCP_PROJECT_DIR"] == str(project)


def test_gemini_home_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["config", "--client", "gemini", "--write"]) == 0
    data = json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    assert data["mcpServers"]["godot-mcp"]["command"] == "uvx"
    assert "env" not in data["mcpServers"]["godot-mcp"]
