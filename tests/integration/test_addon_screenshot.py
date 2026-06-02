"""Integration test: the screenshot PNG-encode path (issue #33).

Runs ``godot/tests/screenshot_smoke.gd`` headless and decodes its base64 output to
confirm the addon produces a valid PNG. The actual editor-viewport capture is not
headless-testable (no rendering) and is verified manually.
"""

from __future__ import annotations

import base64

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_screenshot_encode_produces_valid_png() -> None:
    result = run_godot(["--script", "res://tests/screenshot_smoke.gd"])
    output = result.stdout + result.stderr
    assert "SCREENSHOT_TEST_OK" in output, f"smoke failed (exit {result.returncode}):\n{output}"

    b64_lines = [
        line[len("SCREENSHOT_B64:") :]
        for line in output.splitlines()
        if line.startswith("SCREENSHOT_B64:")
    ]
    assert b64_lines, f"no SCREENSHOT_B64 line in output:\n{output}"
    data = base64.b64decode(b64_lines[0], validate=True)
    assert data.startswith(PNG_SIGNATURE), "addon did not produce a valid PNG"
