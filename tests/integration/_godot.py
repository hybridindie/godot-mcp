"""Helpers for driving the Godot editor headlessly from integration tests.

The addon is GDScript that only runs inside Godot, so these tests shell out to
the Godot binary. They are gated with ``@pytest.mark.skipif`` on the binary being
absent — a genuine environmental precondition, the one conditional skip the
testing rules permit (CI has no editor; a dev machine with Godot 4.4+ does).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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


# Engine-side watchdog: Godot quits after this many main-loop iterations no matter
# what, so an orphaned headless run (parent pytest killed mid-smoke, where the
# subprocess timeout can never fire) self-terminates instead of leaking. Far above
# any legit smoke's frame budget (the heaviest quits itself after ~3 frames), and an
# idle/errored loop burns through it near-instantly, so normal runs are unaffected.
QUIT_AFTER_FRAMES = 1800


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


async def serve_and_await_editor(bridge: object, attempts: int = 120, delay: float = 0.5) -> bool:
    """Inverted-bridge e2e setup (#276): start the server's listener, then wait for the
    Godot addon (the client) to connect out to it. The editor is launched separately by
    the caller; the addon reconnects with backoff, so launch order doesn't matter.
    Returns whether the editor connected within the budget."""
    import asyncio

    await bridge.serve()  # type: ignore[attr-defined]
    for _ in range(attempts):
        if bridge.connected:  # type: ignore[attr-defined]
            return True
        await asyncio.sleep(delay)
    # Timed out: callers raise before their `finally: bridge.close()`, so release the
    # listener here or its port leaks and breaks the rest of the suite (#276 review).
    await bridge.close()  # type: ignore[attr-defined]
    return False
