"""VCS snapshot backstop (#760).

Git snapshots for changes outside the UndoRedo stack (file writes, settings,
over-threshold batches). Snapshots are commits on a private
``refs/godot-mcp/snapshots/*`` ref built through a temporary index, so the
user's HEAD, branch, index and working tree are untouched by *snapshotting*.
Restore overwrites the snapshot's files in the worktree (extra files created
afterwards are left in place and reported).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import ErrorCode
from mcp_server.models.vcs import VcsRestoreResult, VcsSnapshotResult
from mcp_server.runtime import resolve_project_dir
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    PreconditionError,
    enforce_preconditions,
    require_confirmation,
)

_MAX_SNAPSHOTS = 50
_GIT_TIMEOUT = 30.0


class _GitError(PreconditionError):
    pass


async def _git(
    project: Path, *args: str, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    if shutil.which("git") is None:
        raise PreconditionError(
            "git is not installed; the VCS backstop needs git on PATH.",
            required="git",
        )
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(project),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise PreconditionError(
            f"git {' '.join(args[:2])} timed out after {_GIT_TIMEOUT:g}s.",
            required="git",
        ) from None
    code = proc.returncode if proc.returncode is not None else 1
    return code, out.decode(errors="replace"), err.decode(errors="replace")


async def _repo_root(project: str) -> Path:
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise PreconditionError(
            f"Project directory '{project}' does not exist.", required="project_dir"
        )
    rc, out, err = await _git(root, "rev-parse", "--show-toplevel")
    if rc != 0:
        raise PreconditionError(
            f"'{root}' is not a git repository; run git init first.",
            required="git_repo",
        )
    top = Path(out.strip()).resolve()
    if top != root:
        raise PreconditionError(
            f"The git repository root is '{top}', not the project root '{root}'. "
            "Snapshots require the project to be the repository root.",
            required="git_repo_root",
        )
    return root


async def _current_files(root: Path) -> set[str]:
    rc, out, err = await _git(root, "ls-files", "-z", "-co", "--exclude-standard")
    if rc != 0:
        raise _GitError(f"git ls-files failed: {err.strip()}", required="git")
    return {p for p in out.split("\0") if p}


async def _tree_files(root: Path, commit: str) -> set[str]:
    rc, out, err = await _git(root, "ls-tree", "-r", "-z", "--name-only", commit)
    if rc != 0:
        raise _GitError(f"git ls-tree failed: {err.strip()}", required="git")
    return {p for p in out.split("\0") if p}


async def _make_snapshot(root: Path, label: str) -> tuple[str, set[str]]:
    fd, index_path = tempfile.mkstemp(prefix="godot-mcp-index-")
    os.close(fd)
    os.unlink(index_path)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = index_path
    try:
        rc, _, err = await _git(root, "add", "-A", "--", ".", env=env)
        if rc != 0:
            raise _GitError(f"git add failed: {err.strip()}", required="git")
        rc, tree, err = await _git(root, "write-tree", env=env)
        if rc != 0:
            raise _GitError(f"git write-tree failed: {err.strip()}", required="git")
        message = f"godot-mcp snapshot {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        if label:
            message += f": {label}"
        rc, commit, err = await _git(
            root,
            "-c",
            "user.name=godot-mcp",
            "-c",
            "user.email=godot-mcp@localhost",
            "commit-tree",
            tree.strip(),
            "-m",
            message,
            env=env,
        )
        if rc != 0:
            raise _GitError(f"git commit-tree failed: {err.strip()}", required="git")
        return commit.strip(), await _tree_files(root, commit.strip())
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass


def _snapshot_error(snapshot_id: str) -> PreconditionError:
    return PreconditionError(
        f"No snapshot '{snapshot_id}'. Create one with godot_vcs_snapshot.",
        required="snapshot_id",
        error=ErrorCode.RESOURCE_NOT_FOUND,
    )


def register_vcs(mcp: FastMCP, bridge: Bridge, config: ServerConfig) -> None:
    """Register vcs_snapshot / vcs_restore (core)."""
    store: dict[str, dict[str, Any]] = {}
    counter = 0

    async def _project() -> Path:
        return await _repo_root(await resolve_project_dir(bridge, config))

    @mcp.tool(meta=MUTATING, tags={CORE_TAG})
    @enforce_preconditions
    async def vcs_snapshot(label: str = "", dry_run: bool = False) -> VcsSnapshotResult:
        """Snapshot the project's tracked and untracked files on a private git ref.

        The backstop for changes outside the UndoRedo stack (file writes, settings,
        over-threshold batches). Does not touch HEAD, the branch, the index or the
        working tree. Returns an id for godot_vcs_restore. The project must be the
        root of a git repository. ``dry_run`` reports the file count without
        creating a ref.
        """
        nonlocal counter
        root = await _project()
        if not counter:
            rc, out, _ = await _git(
                root, "for-each-ref", "--format=%(refname)", "refs/godot-mcp/snapshots"
            )
            if rc == 0:
                ids = [
                    int(r.rsplit("/v", 1)[-1])
                    for r in out.splitlines()
                    if r.rsplit("/v", 1)[-1].isdigit()
                ]
                counter = max(ids, default=0)
        if dry_run:
            files = await _current_files(root)
            return VcsSnapshotResult(
                label=label or None,
                files_snapshotted=len(files),
                dry_run=True,
            )
        commit, files = await _make_snapshot(root, label)
        counter += 1
        snapshot_id = f"v{counter}"
        ref = f"refs/godot-mcp/snapshots/{snapshot_id}"
        rc, _, err = await _git(root, "update-ref", ref, commit)
        if rc != 0:
            raise _GitError(f"git update-ref failed: {err.strip()}", required="git")
        store[snapshot_id] = {
            "label": label or None,
            "ref": ref,
            "commit": commit,
            "files": files,
            "created_at": time.time(),
        }
        while len(store) > _MAX_SNAPSHOTS:
            old_id = next(iter(store))
            old = store.pop(old_id)
            await _git(root, "update-ref", "-d", str(old["ref"]))
        return VcsSnapshotResult(
            snapshot_id=snapshot_id,
            label=label or None,
            ref=ref,
            commit=commit,
            files_snapshotted=len(files),
        )

    @mcp.tool(meta=DESTRUCTIVE, tags={CORE_TAG})
    @enforce_preconditions
    async def vcs_restore(
        snapshot_id: str, confirm: bool = False, dry_run: bool = False
    ) -> VcsRestoreResult:
        """Restore a VCS snapshot's files into the project (destructive).

        Overwrites the snapshot's files in the working tree via a temporary index;
        HEAD, the branch and the real index are untouched. Files created after the
        snapshot are left in place and counted in ``extra_files``. Requires
        ``confirm=True``. ``dry_run`` previews the file counts.
        """
        root = await _project()
        entry = store.get(snapshot_id)
        if entry is None:
            ref = f"refs/godot-mcp/snapshots/{snapshot_id}"
            rc, out, _ = await _git(root, "rev-parse", "--verify", ref)
            if rc != 0:
                raise _snapshot_error(snapshot_id)
            commit = out.strip()
            entry = {
                "label": None,
                "ref": ref,
                "commit": commit,
                "files": await _tree_files(root, commit),
                "created_at": None,
            }
        current = await _current_files(root)
        extra = current - set(entry["files"])
        if dry_run:
            return VcsRestoreResult(
                snapshot_id=snapshot_id,
                label=entry["label"],
                files_restored=len(entry["files"]),
                extra_files=len(extra),
                dry_run=True,
            )
        require_confirmation(confirm, "vcs_restore")
        fd, index_path = tempfile.mkstemp(prefix="godot-mcp-restore-")
        os.close(fd)
        os.unlink(index_path)
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = index_path
        try:
            rc, _, err = await _git(root, "read-tree", str(entry["commit"]), env=env)
            if rc != 0:
                raise _GitError(f"git read-tree failed: {err.strip()}", required="git")
            rc, _, err = await _git(root, "checkout-index", "-a", "-f", env=env)
            if rc != 0:
                raise _GitError(
                    f"git checkout-index failed: {err.strip()}", required="git"
                )
        finally:
            try:
                os.unlink(index_path)
            except FileNotFoundError:
                pass
        return VcsRestoreResult(
            snapshot_id=snapshot_id,
            label=entry["label"],
            restored=True,
            files_restored=len(entry["files"]),
            extra_files=len(extra),
            hint=(
                f"{len(extra)} file(s) created after the snapshot were left in place."
                if extra
                else None
            ),
        )
