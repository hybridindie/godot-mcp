"""Integration: git snapshot/restore backstop (#760)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("one", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-q", "-m", "init")


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "bridge unused")


def _server(root: Path) -> FastMCP:
    config = ServerConfig(bridge=BridgeConfig(), godot_project_dir=str(root))
    bridge = Bridge(
        config.bridge, connector=connector_for(FakeAddonConnection(responder=_responder))
    )
    return create_server(config, bridge=bridge)


async def test_snapshot_restore_round_trip_leaves_head_and_index_alone(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("new", encoding="utf-8")
    head_before = _git(tmp_path, "rev-parse", "HEAD")
    index_before = _git(tmp_path, "ls-files", "-s")
    async with Client(_server(tmp_path), mode="legacy") as client:
        snap = await client.call_tool("godot_vcs_snapshot", {"label": "before"})
        assert snap.structured_content["files_snapshotted"] == 2
        assert _git(tmp_path, "rev-parse", "HEAD") == head_before
        assert _git(tmp_path, "ls-files", "-s") == index_before
        assert _git(tmp_path, "for-each-ref", "refs/godot-mcp/snapshots").count("v1") == 1

        (tmp_path / "a.txt").write_text("two", encoding="utf-8")
        (tmp_path / "untracked.txt").unlink()
        (tmp_path / "extra.txt").write_text("extra", encoding="utf-8")
        restored = await client.call_tool(
            "godot_vcs_restore",
            {"snapshot_id": snap.structured_content["snapshot_id"], "confirm": True},
        )
    assert restored.structured_content["restored"] is True
    assert restored.structured_content["files_restored"] == 2
    assert restored.structured_content["extra_files"] == 1
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one"
    assert (tmp_path / "untracked.txt").read_text(encoding="utf-8") == "new"
    assert (tmp_path / "extra.txt").read_text(encoding="utf-8") == "extra"
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before
    assert _git(tmp_path, "ls-files", "-s") == index_before


async def test_dry_run_and_refusals(tmp_path: Path) -> None:
    _repo(tmp_path)
    async with Client(_server(tmp_path), mode="legacy") as client:
        preview = await client.call_tool("godot_vcs_snapshot", {"dry_run": True})
        assert preview.structured_content["dry_run"] is True
        assert preview.structured_content["files_snapshotted"] == 1
        assert _git(tmp_path, "for-each-ref", "refs/godot-mcp/snapshots") == ""

        snap = await client.call_tool("godot_vcs_snapshot", {})
        sid = snap.structured_content["snapshot_id"]
        preview = await client.call_tool(
            "godot_vcs_restore", {"snapshot_id": sid, "dry_run": True}
        )
        assert preview.structured_content["restored"] is False
        refused = await client.call_tool(
            "godot_vcs_restore", {"snapshot_id": sid}, raise_on_error=False
        )
        assert refused.structured_content["error"] == "PRECONDITION_FAILED"
        missing = await client.call_tool(
            "godot_vcs_restore", {"snapshot_id": "v99"}, raise_on_error=False
        )
        assert missing.structured_content["error"] == "RESOURCE_NOT_FOUND"


async def test_snapshot_survives_a_server_restart(tmp_path: Path) -> None:
    _repo(tmp_path)
    async with Client(_server(tmp_path), mode="legacy") as client:
        first = await client.call_tool("godot_vcs_snapshot", {})
        first_id = first.structured_content["snapshot_id"]
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    async with Client(_server(tmp_path), mode="legacy") as client:
        restored = await client.call_tool(
            "godot_vcs_restore", {"snapshot_id": first_id, "confirm": True}
        )
        second = await client.call_tool("godot_vcs_snapshot", {})
    assert restored.structured_content["restored"] is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one"
    assert second.structured_content["snapshot_id"] != first_id


async def test_not_a_git_repository_is_a_clear_precondition(tmp_path: Path) -> None:
    async with Client(_server(tmp_path), mode="legacy") as client:
        result = await client.call_tool("godot_vcs_snapshot", {}, raise_on_error=False)
    assert result.structured_content["error"] == "PRECONDITION_FAILED"
    assert "not a git repository" in result.structured_content["hint"]
