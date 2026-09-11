"""Contract tests pinning the e2e contention fix (issue #444).

The e2e suites run on a single self-hosted runner whose jobs can overlap across
PRs (each PR gets its own ``concurrency`` group, but different PRs don't gate
each other). Three properties keep concurrent runs from interfering:

1. No e2e file hard-codes the bridge port — every listener/editor pair gets an
   ephemeral port from :func:`tests.integration._godot.e2e_bridge_url`, so a
   stale/orphaned editor from another job can never answer the wrong test.
2. The e2e workflow serializes live-editor runs with a repo-wide ``concurrency``
   mutex so two live-editor jobs never share the runner at the same time.
3. The bridge-connect wait retries the *whole* editor-boot path with bounded
   backoff instead of one fixed-deadline poll loop that a cold, contended
   editor can miss.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

import yaml

from tests.integration._godot import e2e_bridge_url, serve_and_await_editor

# The async tests in this module; pytest-asyncio's auto mode (pyproject) runs
# them without a global mark, so sync tests aren't mis-marked.

_REPO_ROOT = Path(__file__).resolve().parents[2]
_E2E_DIR = _REPO_ROOT / "tests" / "integration"

# The fixed test port the suites used before #444; hard-coding any port in an
# e2e file reintroduces cross-job contention (issue #444).
_LEGACY_PORT = re.compile(r"BRIDGE_URL\s*=\s*[\"']ws://127\.0\.0\.1:\d+[\"']")


def _e2e_files() -> list[Path]:
    return sorted(_E2E_DIR.glob("test_*_e2e.py"))


def test_no_e2e_file_hardcodes_a_bridge_port() -> None:
    offenders = [
        path.name
        for path in _e2e_files()
        if _LEGACY_PORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "e2e files must derive their bridge URL from tests.integration._godot."
        "e2e_bridge_url() (per-process ephemeral port, issue #444); "
        f"hard-coded: {offenders}"
    )


def test_e2e_workflow_serializes_live_editor_runs() -> None:
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "e2e.yml").read_text(encoding="utf-8")
    )
    concurrency = workflow["concurrency"]
    # A repo-wide group (not per-ref): two different PRs' live-editor jobs are
    # exactly the overlap #444 documents, so the group must span the repo.
    assert concurrency["group"] == "e2e", concurrency
    # Superseded pushes within one PR should still cancel in place.
    assert concurrency["cancel-in-progress"] is True


def test_e2e_bridge_url_is_loopback_ephemeral_and_free() -> None:
    # The OS may hand the same ephemeral port to two sequential probes (it reuses
    # the ephemeral range freely once closed), so *uniqueness across calls* is not
    # the contract — what matters: loopback form, never the legacy fixed ports the
    # suites shared before #444, and the port is free to bind right now.
    url = e2e_bridge_url()
    assert url.startswith("ws://127.0.0.1:")
    port = int(url.removeprefix("ws://127.0.0.1:"))
    assert 1 <= port <= 65535
    assert port not in (9097, 9098)  # the fixed ports behind the #444 collisions
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))  # free at allocation time: a listener can take it


async def test_serve_and_await_editor_retries_serve_on_bind_conflict() -> None:
    # Another process holds the port (a concurrent job's listener): the wait must
    # retry the whole serve/connect path with backoff, not die on the first
    # bind conflict.
    class _FlakyBridge:
        def __init__(self) -> None:
            self.serve_calls = 0
            self.connected = False

        async def serve(self) -> None:
            self.serve_calls += 1
            if self.serve_calls == 1:
                raise OSError("address already in use")
            self.connected = True

        async def close(self) -> None:
            self.connected = False

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    flaky = _FlakyBridge()
    connected = await serve_and_await_editor(
        flaky,
        attempts=5,
        delay=0.25,
        sleep=fake_sleep,
    )
    assert connected is True
    assert flaky.serve_calls == 2  # one conflict, then success
    # Backoff is bounded and grows from the base delay (no bare fixed waits).
    assert sleeps == [0.25]


async def test_serve_and_await_editor_gives_up_bounded_and_releases_listener() -> None:
    class _NeverBridge:
        def __init__(self) -> None:
            self.connected = False
            self.closed = False

        async def serve(self) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    never = _NeverBridge()
    connected = await serve_and_await_editor(
        never,
        attempts=4,
        delay=0.5,
        sleep=fake_sleep,
    )
    assert connected is False
    assert never.closed is True  # listener released so the port can't leak
    # Exponential backoff between rounds, capped by 8*delay: 0.5, 1.0, 2.0 —
    # the last round has no trailing sleep.
    assert sleeps == [0.5, 1.0, 2.0]