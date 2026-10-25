"""Contract tests for the VCS snapshot backstop (#760, coverage #795).

The tools shell out to ``git``, so these use a **real temporary repository** —
that exercises the ref/index machinery the unit suite previously skipped
(``vcs.py`` was at 25% in unit+contract). No Godot process is involved: the
project dir comes from config and the bridge is a fake.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.tools import vcs
from tests.fakes import FakeAddonConnection, connector_for


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=30)
    (tmp_path / "game.gd").write_text("v1\n", encoding="utf-8")
    return tmp_path.resolve()


def _server(project: Path) -> FastMCP:
    config = ServerConfig(godot_project_dir=str(project))
    bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(config, bridge=bridge)


async def _call(client: Any, tool: str, **arguments: Any) -> Any:
    return await client.call_tool(tool, arguments, raise_on_error=False)


def _snapshot_refs(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "for-each-ref", "--format=%(refname)"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return [line for line in out.stdout.splitlines() if line.startswith("refs/godot-mcp/")]


@pytest.mark.asyncio
async def test_snapshot_and_restore_roundtrip_leaves_extra_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    async with Client(_server(repo)) as client:
        snap = await _call(client, "godot_vcs_snapshot", label="before")
        assert snap.is_error is False, snap
        snapshot_id = snap.structured_content["snapshot_id"]
        assert snapshot_id == "v1"
        assert snap.structured_content["files_snapshotted"] >= 1

        (repo / "game.gd").write_text("v2\n", encoding="utf-8")
        (repo / "extra.txt").write_text("created later\n", encoding="utf-8")

        restored = await _call(client, "godot_vcs_restore", snapshot_id=snapshot_id, confirm=True)

    assert restored.is_error is False, restored
    assert restored.structured_content["restored"] is True
    assert restored.structured_content["extra_files"] == 1
    assert "left in place" in restored.structured_content["hint"]
    assert (repo / "game.gd").read_text(encoding="utf-8") == "v1\n"
    assert (repo / "extra.txt").exists()


@pytest.mark.asyncio
async def test_snapshot_dry_run_creates_no_ref(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    async with Client(_server(repo)) as client:
        result = await _call(client, "godot_vcs_snapshot", dry_run=True)

    assert result.is_error is False, result
    assert result.structured_content["dry_run"] is True
    assert result.structured_content["files_snapshotted"] >= 1
    assert result.structured_content["snapshot_id"] is None
    assert _snapshot_refs(repo) == []


@pytest.mark.asyncio
async def test_restore_requires_confirm_and_changes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    async with Client(_server(repo)) as client:
        snap = await _call(client, "godot_vcs_snapshot")
        snapshot_id = snap.structured_content["snapshot_id"]
        (repo / "game.gd").write_text("v2\n", encoding="utf-8")

        refused = await _call(client, "godot_vcs_restore", snapshot_id=snapshot_id)

    assert refused.is_error
    assert refused.structured_content["error"] == "PRECONDITION_FAILED"
    assert refused.structured_content["required"] == "confirm"
    assert (repo / "game.gd").read_text(encoding="utf-8") == "v2\n"


@pytest.mark.asyncio
async def test_restore_dry_run_previews_without_writing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    async with Client(_server(repo)) as client:
        snap = await _call(client, "godot_vcs_snapshot")
        snapshot_id = snap.structured_content["snapshot_id"]
        (repo / "game.gd").write_text("v2\n", encoding="utf-8")

        preview = await _call(
            client, "godot_vcs_restore", snapshot_id=snapshot_id, confirm=True, dry_run=True
        )

    assert preview.is_error is False, preview
    assert preview.structured_content["dry_run"] is True
    assert preview.structured_content["files_restored"] >= 1
    assert (repo / "game.gd").read_text(encoding="utf-8") == "v2\n"


@pytest.mark.asyncio
async def test_unknown_snapshot_is_resource_not_found(tmp_path: Path) -> None:
    async with Client(_server(_repo(tmp_path))) as client:
        result = await _call(client, "godot_vcs_restore", snapshot_id="v999")

    assert result.is_error
    assert result.structured_content["error"] == "RESOURCE_NOT_FOUND"
    assert result.structured_content["required"] == "snapshot_id"


@pytest.mark.asyncio
async def test_restore_resolves_a_ref_from_a_fresh_server(tmp_path: Path) -> None:
    """The store is per-server; a restarted server must find the ref on disk."""
    repo = _repo(tmp_path)
    async with Client(_server(repo)) as first:
        snap = await _call(first, "godot_vcs_snapshot")
    snapshot_id = snap.structured_content["snapshot_id"]
    (repo / "game.gd").write_text("v2\n", encoding="utf-8")

    async with Client(_server(repo)) as second:
        restored = await _call(
            second, "godot_vcs_restore", snapshot_id=snapshot_id, confirm=True
        )

    assert restored.is_error is False, restored
    assert (repo / "game.gd").read_text(encoding="utf-8") == "v1\n"


@pytest.mark.asyncio
async def test_project_that_is_not_a_git_repo_is_refused(tmp_path: Path) -> None:
    async with Client(_server(tmp_path.resolve())) as client:
        result = await _call(client, "godot_vcs_snapshot")

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "git_repo"


@pytest.mark.asyncio
async def test_project_must_be_the_repository_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    nested = repo / "game"
    nested.mkdir()

    async with Client(_server(nested)) as client:
        result = await _call(client, "godot_vcs_snapshot")

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "git_repo_root"


@pytest.mark.asyncio
async def test_missing_git_binary_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcp_server.tools.vcs.shutil.which", lambda _name: None)

    async with Client(_server(_repo(tmp_path))) as client:
        result = await _call(client, "godot_vcs_snapshot")

    assert result.is_error
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert result.structured_content["required"] == "git"
