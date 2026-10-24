"""Unit: doctor reports actionable failures (#762)."""

from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import mcp_server
from mcp_server import cli


class _Socket:
    def __enter__(self) -> _Socket:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _project(tmp_path: Path, *, with_addon: bool = True) -> Path:
    project = tmp_path / "game"
    project.mkdir()
    plugins = ""
    if with_addon:
        addon = project / "addons" / "godot_mcp"
        addon.mkdir(parents=True)
        (addon / "plugin.cfg").write_text(
            f'[plugin]\nname="godot_mcp"\nversion="{mcp_server.__version__}"\n',
            encoding="utf-8",
        )
        plugins = '\n[editor_plugins]\nenabled=PackedStringArray("res://addons/godot_mcp/plugin.cfg")\n'
    (project / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="Game"\n' + plugins,
        encoding="utf-8",
    )
    return project


def test_doctor_all_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(cli, "find_godot_binary", lambda config: "/fake/godot")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Godot 4.7.2\n", stderr=""),
    )
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: _Socket())
    assert cli.main(["doctor", "--project", str(project)]) == 0


def test_doctor_missing_addon_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path, with_addon=False)
    monkeypatch.setattr(cli, "find_godot_binary", lambda config: "/fake/godot")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Godot 4.7.2\n", stderr=""),
    )
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: _Socket())
    assert cli.main(["doctor", "--project", str(project)]) == 1
    output = capsys.readouterr().out
    assert "fix: install the addon" in output


def test_doctor_unreachable_bridge_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(cli, "find_godot_binary", lambda config: "/fake/godot")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="Godot 4.7.2\n", stderr=""),
    )

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", refuse)
    assert cli.main(["doctor", "--project", str(project)]) == 1
    assert "fix: start the server" in capsys.readouterr().out
