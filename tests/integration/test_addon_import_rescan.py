"""Integration test: the resilient import rescan (issue #628).

Runs the headless GDScript exerciser ``godot/tests/import_rescan_smoke.gd`` and
asserts it reports success. This pins ``MCPImportAssetHandlers.ensure_scan``
against the real Godot runtime: a scan is started when none is in flight, and
deferred when one already is — so a copied file is never silently missed.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_import_rescan_never_stacks_scans() -> None:
    result = run_godot(["--script", "res://tests/import_rescan_smoke.gd"])
    output = result.stdout + result.stderr
    assert "IMPORT_RESCAN_OK" in output, (
        f"import-rescan smoke test did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
