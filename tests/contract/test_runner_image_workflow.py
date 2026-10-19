"""Contract: the runner-image workflow does not push on routine ``main`` builds.

Issue #706: the ``godot-mcp-runner`` GHCR package currently refuses the repo's
``GITHUB_TOKEN`` (``permission_denied: write_package``). A push to ``main`` that
touches the Dockerfile therefore leaves a red run. Until the package grants
write access, push events build the image (validating the Dockerfile) and only
a manual dispatch pushes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "runner-image.yml"


def _steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return cast("list[dict[str, Any]]", workflow["jobs"]["build"]["steps"])


def test_runner_image_only_pushes_on_manual_dispatch() -> None:
    build = next(
        step
        for step in _steps()
        if str(step.get("uses", "")).startswith("docker/build-push-action")
    )
    assert build["with"]["push"] == "${{ github.event_name == 'workflow_dispatch' }}"


def test_runner_image_skips_the_ghcr_login_on_push_builds() -> None:
    login = next(
        step for step in _steps() if str(step.get("uses", "")).startswith("docker/login-action")
    )
    assert login.get("if") == "github.event_name == 'workflow_dispatch'"
