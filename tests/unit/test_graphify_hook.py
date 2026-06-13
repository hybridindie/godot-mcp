"""Unit test for the graphify git-hook refresh predicate (issue #174).

The hook (`scripts/hooks/_graphify_refresh.sh`, shared by post-commit/post-merge)
must run `scripts/graphify.sh update .` after a commit ONLY when graph-relevant
MCP source changed (`mcp_server/**/*.py` or `godot/addons/godot_mcp/**/*.gd`),
and no-op otherwise. The test is hermetic: it stubs `scripts/graphify.sh` so no
real graphify install is required.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFRESH = REPO_ROOT / "scripts" / "hooks" / "_graphify_refresh.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    # Stub graphify.sh: record its args to ran.log instead of running graphify.
    hooks = repo / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    (REFRESH).read_text()  # ensure the real script exists (red until created)
    stub = repo / "scripts" / "graphify.sh"
    stub.write_text(
        '#!/usr/bin/env bash\n'
        'echo "$@" >> "$(git rev-parse --show-toplevel)/ran.log"\n'
    )
    stub.chmod(0o755)
    # Guard precondition: pretend graphify is set up in this checkout.
    (repo / "graphify-out").mkdir()
    (repo / "graphify-out" / ".graphify_python").write_text("/usr/bin/env python3\n")
    return repo


def _run_hook(repo: Path) -> None:
    subprocess.run([str(REFRESH)], cwd=repo, check=False, capture_output=True, env={**os.environ})


def _commit(repo: Path, rel: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"touch {rel}")


@pytest.mark.parametrize(
    "rel",
    ["mcp_server/tools/health.py", "godot/addons/godot_mcp/handlers/mutation.gd"],
)
def test_hook_runs_update_on_relevant_change(tmp_path: Path, rel: str) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, rel)
    _run_hook(repo)
    log = repo / "ran.log"
    assert log.exists(), f"hook did not invoke graphify.sh for {rel}"
    assert "update ." in log.read_text()


@pytest.mark.parametrize("rel", ["README.md", "docs/architecture.md", "evals/foo.py"])
def test_hook_noops_on_irrelevant_change(tmp_path: Path, rel: str) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, rel)
    _run_hook(repo)
    assert not (repo / "ran.log").exists(), f"hook should have no-opped for {rel}"


def test_hook_noops_when_graphify_not_setup(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "graphify-out" / ".graphify_python").unlink()  # not set up
    _commit(repo, "mcp_server/tools/health.py")
    _run_hook(repo)
    assert not (repo / "ran.log").exists()
