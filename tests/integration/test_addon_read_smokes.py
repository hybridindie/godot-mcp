"""Integration test: the headless read-helper smoke scripts pass (#467).

Each ``godot/tests/<name>_smoke.gd`` builds real Godot objects, checks one addon helper,
and prints its ``*_TEST_OK`` marker. These scripts were never wired into pytest, so CI
never ran them. A ``SCRIPT ERROR`` also fails the run: a check aborted by a script error
records no failure, so the marker alone can't be trusted.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

SMOKES = [
    ("animation_read_smoke.gd", "ANIM_READ_TEST_OK"),
    ("audio_bus_capture_smoke.gd", "AUDIO_BUS_CAPTURE_TEST_OK"),
    ("input_action_read_smoke.gd", "INPUT_ACTION_READ_TEST_OK"),
    ("particle_read_smoke.gd", "PARTICLE_READ_TEST_OK"),
    ("run_commands_smoke.gd", "RUN_COMMANDS_TEST_OK"),
    ("theme_read_smoke.gd", "THEME_READ_TEST_OK"),
    ("visual_shader_read_smoke.gd", "VISUAL_SHADER_READ_TEST_OK"),
]


@pytest.mark.parametrize(("script", "marker"), SMOKES, ids=[s for s, _ in SMOKES])
def test_read_helper_smoke(script: str, marker: str) -> None:
    result = run_godot(["--script", f"res://tests/{script}"])
    output = result.stdout + result.stderr
    assert marker in output, f"{script} did not pass (exit {result.returncode}):\n{output}"
    assert result.returncode == 0, f"{script}: expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output, f"{script} raised a script error:\n{output}"
