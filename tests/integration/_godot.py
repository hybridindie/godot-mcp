"""Helpers for driving the Godot editor headlessly from integration tests.

The addon is GDScript that only runs inside Godot, so these tests shell out to
the Godot binary. They are gated with ``@pytest.mark.skipif`` on the binary being
absent — a genuine environmental precondition, the one conditional skip the
testing rules permit (CI has no editor; a dev machine with Godot 4.4+ does).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GODOT_PROJECT = REPO_ROOT / "godot"

# Common macOS install location; extend as needed for other platforms.
_MAC_APP = Path("/Applications/Godot.app/Contents/MacOS/Godot")


def find_godot() -> str | None:
    """Locate a Godot binary: ``$GODOT_BIN`` → ``PATH`` → known app bundle."""
    env_bin = os.environ.get("GODOT_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    on_path = shutil.which("godot") or shutil.which("Godot")
    if on_path:
        return on_path
    if _MAC_APP.is_file():
        return str(_MAC_APP)
    return None


GODOT_BIN = find_godot()


def _has_display() -> bool:
    """Whether a display server is available for play sessions.

    macOS always has a display (CoreGraphics). Linux needs ``$DISPLAY`` set
    (a real X11/Wayland session or an xvfb wrapper). A headless CI container
    has neither, so play-session tests skip there — they're dev-machine tests
    that need a running game window, not something ``--headless`` can provide.
    """
    import sys

    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


# A pytest marker for tests that need a display (play sessions, runtime
# inspection, input simulation, profiling, input recording). Skip in headless
# CI; run on a dev machine with a real Godot editor and display.
needs_display = pytest.mark.skipif(
    not _has_display(),
    reason="Play-session test — needs a display server (run on a dev machine, not headless CI)",
)


# Engine-side watchdog: Godot quits after this many main-loop iterations no matter
# what, so an orphaned headless run (parent pytest killed mid-smoke, where the
# subprocess timeout can never fire) self-terminates instead of leaking. Far above
# any legit smoke's frame budget (the heaviest quits itself after ~3 frames), and an
# idle/errored loop burns through it near-instantly, so normal runs are unaffected.
QUIT_AFTER_FRAMES = 1800


def e2e_bridge_url() -> str:
    """A fresh loopback bridge URL on an ephemeral, currently-free port (issue #444).

    Each e2e session binds its listener and editor to its own port so a
    concurrent job's (or an orphaned) editor can never connect to the wrong
    test's listener. The port is grabbed via an ephemeral bind and closed again;
    the listener rebinds it moments later, so on loopback the race window is
    negligible.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"ws://127.0.0.1:{port}"


def run_godot(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run the Godot binary against the addon project and capture output.

    ``args`` are appended after ``--headless --quit-after <n> --path <godot project>``.
    """
    assert GODOT_BIN is not None, "run_godot called without a Godot binary"
    cmd = [
        GODOT_BIN,
        "--headless",
        "--quit-after",
        str(QUIT_AFTER_FRAMES),
        "--path",
        str(GODOT_PROJECT),
        *args,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


async def serve_and_await_editor(
    bridge: object,
    attempts: int = 5,
    delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> bool:
    """Inverted-bridge e2e setup (#276): start the server's listener, then wait for the
    Godot addon (the client) to connect out to it. The editor is launched separately by
    the caller; the addon reconnects with backoff, so launch order doesn't matter.
    Returns whether the editor connected within the budget.

    Contention-aware (#444): the whole serve/connect setup is retried across
    ``attempts`` rounds with exponential backoff between rounds (capped at
    ``8 * delay``), so a cold/contended editor boot — or a listener port a
    concurrent job still holds (bind conflict) — fails into a retry instead of
    failing the run. Each round polls for the addon for up to 24 ticks of
    ``delay``; a round that times out releases the listener before the next one
    so the port can't leak. ``sleep`` is injectable for deterministic tests; with
    it, poll ticks do not sleep (only the between-round backoff does).
    """
    import asyncio

    doze = sleep or asyncio.sleep
    for attempt in range(attempts):
        try:
            await bridge.serve()  # type: ignore[attr-defined]
        except OSError:
            # Bind conflict: another listener still holds the port. Back off and
            # retry the whole setup rather than failing the run (#444).
            if attempt < attempts - 1:
                await doze(min(8 * delay, delay * 2**attempt))
            continue
        for _ in range(24):
            if bridge.connected:  # type: ignore[attr-defined]
                return True
            if sleep is None:
                await doze(delay)
        # The addon never connected on this round: release the listener before
        # retrying so the port can't leak across rounds (#276 review).
        await bridge.close()  # type: ignore[attr-defined]
        if attempt < attempts - 1:
            await doze(min(8 * delay, delay * 2**attempt))
    # Timed out: callers raise before their `finally: bridge.close()`, so release the
    # listener here or its port leaks and breaks the rest of the suite (#276 review).
    await bridge.close()  # type: ignore[attr-defined]
    return False
