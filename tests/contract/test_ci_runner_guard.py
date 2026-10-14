"""Contract test: fork PRs must not run on the self-hosted runner (issue #650).

`ci.yml` runs on the maintainer's self-hosted k3s runner. On a public repo a fork
PR can execute arbitrary code there, so every job must be guarded the same way
`e2e.yml` guards its editor job: same-repo branch PRs and pushes run; fork PRs
skip. This pins the guard so a new job can't be added without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_E2E = _REPO_ROOT / ".github" / "workflows" / "e2e.yml"

# The fork distinction: a same-repo PR's head repo is this repo; a fork's is not.
_FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"


def _jobs(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, dict[str, Any]]", data["jobs"])


def test_every_ci_job_skips_fork_prs() -> None:
    offenders = []
    for name, job in _jobs(_CI).items():
        condition = str(job.get("if", ""))
        # Must run on non-PR events (push to main) and same-repo PRs only.
        if "github.event_name != 'pull_request'" not in condition or _FORK_GUARD not in condition:
            offenders.append(name)
    assert not offenders, (
        "every ci.yml job must carry the fork-PR guard (issue #650); missing: "
        + ", ".join(offenders)
    )


def test_ci_jobs_use_the_self_hosted_runner() -> None:
    """Guard against a silent 'guard added but runner changed' — the guard is only
    meaningful while jobs target the self-hosted runner."""
    for name, job in _jobs(_CI).items():
        assert "self-hosted" in str(job.get("runs-on")), name


def test_e2e_guard_matches_ci_guard() -> None:
    """Both workflows protect the same runner with the same predicate."""
    e2e = _jobs(_E2E)["editor-suites"]
    assert _FORK_GUARD in str(e2e.get("if", ""))


def test_no_stale_test_count_comment() -> None:
    """The '642-test suite' comments are stale (#650): the suite is far larger and
    the number drifts every PR — don't hard-code a count."""
    text = _CI.read_text(encoding="utf-8")
    assert "642-test" not in text
