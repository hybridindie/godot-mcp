"""run_godot must pass an engine-side ``--quit-after`` watchdog.

The smoke runner's ``subprocess.run`` timeout only fires while the parent test
process is alive. If a pytest run is interrupted mid-smoke, the headless Godot
child is orphaned and the timeout can never fire — leaking a process that runs
until it quits on its own (observed: smoke editors alive for days). Passing
``--quit-after`` makes the engine self-terminate even when orphaned.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import tests.integration._godot as godot


def test_run_godot_passes_quit_after_watchdog() -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        captured["cmd"] = cmd
        return mock.Mock(returncode=0, stdout="", stderr="")

    with (
        mock.patch.object(godot, "GODOT_BIN", "/fake/godot"),
        mock.patch("tests.integration._godot.subprocess.run", side_effect=fake_run),
    ):
        godot.run_godot(["--script", "res://tests/x_smoke.gd"])

    cmd = captured["cmd"]
    assert "--quit-after" in cmd, f"watchdog flag missing from command: {cmd}"
    # The frame count must follow the flag and be a positive integer.
    n = cmd[cmd.index("--quit-after") + 1]
    assert int(n) > 0
    # The original args must still be present.
    assert "--script" in cmd and "res://tests/x_smoke.gd" in cmd
