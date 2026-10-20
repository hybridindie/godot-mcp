"""Contract tests for the release workflow `publish.yml` (issue #649).

Publishing must build exactly the tagged commit, be gated on the checks passing,
and use SHA-pinned actions (a floating `@release/v1` tag is a supply-chain risk).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PUBLISH = _REPO_ROOT / ".github" / "workflows" / "publish.yml"
_DEPENDABOT = _REPO_ROOT / ".github" / "dependabot.yml"

# `owner/repo@<40-hex-sha>` — a tag/branch ref (e.g. @v4, @release/v1) fails.
_SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
_TAG_REF = "${{ inputs.tag || github.ref }}"


def _workflow() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(_PUBLISH.read_text(encoding="utf-8")))


def _jobs() -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", _workflow()["jobs"])


def _steps(job: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _jobs()[job]["steps"])


def _checkout_step(job: str) -> dict[str, Any]:
    return next(s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/checkout@"))


def test_all_publish_actions_are_sha_pinned() -> None:
    offenders = [
        s["uses"]
        for job in _jobs().values()
        for s in job.get("steps", [])
        if "uses" in s and not _SHA_PIN.match(str(s["uses"]))
    ]
    assert not offenders, "publish.yml actions must be SHA-pinned (#649): " + ", ".join(offenders)


def test_builds_exactly_the_requested_tag() -> None:
    """A manual dispatch with tag=X must check out X, not the default branch."""
    assert _checkout_step("build").get("with", {}).get("ref") == _TAG_REF


def test_docker_publish_builds_the_tagged_commit() -> None:
    assert _checkout_step("publish-docker").get("with", {}).get("ref") == _TAG_REF


def test_publish_is_gated_on_tests() -> None:
    jobs = _jobs()
    assert "test" in jobs, "publish must have a test gate job (#649)"
    needs = jobs["build"].get("needs")
    assert "test" in (needs if isinstance(needs, list) else [needs]), (
        "the build job must need the test job"
    )


def test_test_job_runs_the_suite() -> None:
    runs = " ".join(str(s.get("run", "")) for s in _steps("test"))
    assert "pytest" in runs, "the gate job must run the test suite"


def test_dependabot_keeps_github_actions_fresh() -> None:
    config = yaml.safe_load(_DEPENDABOT.read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"] for u in config["updates"]}
    assert "github-actions" in ecosystems, (
        "SHA-pinned actions need Dependabot to stay current (#649)"
    )


def test_legacy_asset_library_publish_job_is_gone() -> None:
    """#734: the legacy godotengine.org asset-library endpoint uses a different
    ID space and has no valid publish path for the new store. The addon zip is
    attached to the GitHub release and uploaded to store.godotengine.org
    manually until the new store exposes a publish API/CLI."""
    jobs = _jobs()
    assert "publish-assetlib" not in jobs
    text = _PUBLISH.read_text(encoding="utf-8")
    assert "godotengine.org/asset-library" not in text
    assert "YOUR_ASSET_ID" not in text
    assert "GODOT_ASSETLIB_TOKEN" not in text
