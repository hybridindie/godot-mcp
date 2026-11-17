"""Contract test: the Godot 4.8 beta lane has one pin, not two (issue #855).

The beta version and its SHA512 live in two places — the e2e workflow's verified
download fallback and the runner image that bakes the same binary at
``/opt/godot48``. A partial bump (bump one, forget the other) either tests a
snapshot nobody chose or fails the download check, so the Dockerfile's ``ARG``s
are treated as the source of truth and the workflow must agree with them.

The second half pins the removal of the 4.8-beta1 MeshLibrary workaround:
``godotengine/godot#124712`` was fixed before beta2, so a beta-specific branch in
the persistence e2e would now assert the *wrong* saved shape.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_E2E = _REPO_ROOT / ".github" / "workflows" / "e2e.yml"
_DOCKERFILE = _REPO_ROOT / "infra" / "runner.Dockerfile"
_INTEGRATION = _REPO_ROOT / "tests" / "integration"

_SHA512 = r"[0-9a-f]{128}"


def _dockerfile_pin() -> tuple[str, str]:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    version = re.search(r"ARG GODOT48_VERSION=(\S+)", text)
    sha = re.search(rf"ARG GODOT48_SHA512=({_SHA512})", text)
    assert version and sha, "runner.Dockerfile must pin GODOT48_VERSION + GODOT48_SHA512"
    return version.group(1), sha.group(1)


def _workflow_pin() -> tuple[str, str]:
    text = _E2E.read_text(encoding="utf-8")
    version = re.search(r"^\s*version=(\S+)$", text, re.MULTILINE)
    sha = re.search(rf'^\s*sha512="?({_SHA512})"?$', text, re.MULTILINE)
    assert version and sha, "e2e.yml must pin the beta version + SHA512 in the resolve step"
    return version.group(1), sha.group(1)


def test_workflow_and_runner_image_pin_the_same_beta() -> None:
    docker_version, docker_sha = _dockerfile_pin()
    workflow_version, workflow_sha = _workflow_pin()
    assert workflow_version == docker_version, (
        "e2e.yml and runner.Dockerfile pin different Godot betas "
        f"({workflow_version!r} vs {docker_version!r}); bump both together"
    )
    assert workflow_sha == docker_sha, (
        "e2e.yml and runner.Dockerfile pin different SHA512 sums for the beta zip"
    )


def test_beta_download_flavor_matches_the_pinned_version() -> None:
    """``flavor=betaN`` in both download URLs must come from the pinned version."""
    docker_version, _ = _dockerfile_pin()
    flavor = docker_version.replace("4.8-", "")
    for path, text in (
        (_E2E, _E2E.read_text(encoding="utf-8")),
        (_DOCKERFILE, _DOCKERFILE.read_text(encoding="utf-8")),
    ):
        assert re.search(rf"flavor={re.escape(flavor)}&slug=", text), (
            f"{path.name}: download URL flavor must be {flavor!r} (the pinned beta)"
        )


def test_version_guards_accept_the_pinned_beta() -> None:
    """Both the workflow verify step and the image sanity check must match the
    pinned beta's real version string (``4.8.beta3.official.<commit>``), so a
    bump that forgets a regex fails here rather than on the runner."""
    version, _ = _dockerfile_pin()
    sample = f"{version.replace('-', '.')}.official.c51ff06e8"
    workflow = _E2E.read_text(encoding="utf-8")
    image = _DOCKERFILE.read_text(encoding="utf-8")
    guards = [
        re.search(r"if ! printf '%s' \"\$ver\" \| grep -Eq '([^']+)'", workflow),
        re.search(r"/opt/godot48/godot --version \| grep -Eq \"([^\"]+)\"", image),
    ]
    for match in guards:
        assert match, "expected a version guard in both files"
        assert re.search(match.group(1), sample), (
            f"version guard {match.group(1)!r} does not accept the pinned {version!r}"
        )
    # The resolved-download guard must be the same predicate as the verify step.
    pattern = re.search(r"^\s*pattern='([^']+)'$", workflow, re.MULTILINE)
    assert pattern and pattern.group(1) == guards[0].group(1)  # type: ignore[union-attr]


def test_beta_lane_stays_advisory() -> None:
    """The 4.7 lane is the stable gate; a beta regression must be visible but must
    not block a release (remove this only at 4.8-stable)."""
    text = _E2E.read_text(encoding="utf-8")
    assert "godot-4-8-beta:" in text
    assert "continue-on-error: true" in text.split("godot-4-8-beta:", 1)[1]


def test_no_beta_specific_workaround_branches_remain() -> None:
    """Beta-gated known-bad branches must not outlive their upstream fix.

    #124712 (MeshLibrary items saved empty on beta1) was fixed before beta2, so a
    leftover branch would assert a shape later betas no longer produce. The same
    applies to any future ``is_godot_4x_betaN`` shim: remove it when the fix
    lands, don't leave it asserting old behaviour.
    """
    shim = re.compile(r"is_godot_4\d_beta\d")
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in sorted(_INTEGRATION.rglob("*.py"))
        if "124712" in path.read_text(encoding="utf-8")
        or shim.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "beta-gated workarounds must be removed once upstream fixes land; still in: "
        + ", ".join(offenders)
    )
