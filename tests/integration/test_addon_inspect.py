"""Integration test: the inspection serializers behave correctly (issue #5).

Runs the headless GDScript exerciser ``godot/tests/inspect_smoke.gd`` and asserts
it reports success — pinning JSON-safe type coercion, recursive scene
serialization, ``max_depth``, and node-property/info extraction against the real
Godot runtime, with no editor required.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_inspection_serializers() -> None:
    result = run_godot(["--script", "res://tests/inspect_smoke.gd"])
    output = result.stdout + result.stderr
    assert "INSPECT_TEST_OK" in output, (
        f"inspection smoke test did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
