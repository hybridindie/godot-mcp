"""End-to-end runtime test: real headless run + capture (issue #13).

Runs the runtime_probe scene headless through the real GodotRunner and asserts the
captured output + clean exit. Skipped when no Godot binary is present.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_server.config import ServerConfig
from mcp_server.runtime import GodotRunner, summarize_run
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_headless_run_captures_probe_output() -> None:
    runner = GodotRunner(ServerConfig(godot_bin=GODOT_BIN))
    output = asyncio.run(
        runner.run(str(GODOT_PROJECT), "res://tests/runtime_probe.tscn", timeout=60.0)
    )
    result = summarize_run(output)

    assert result.ran is True
    assert result.exit_code == 0, f"unexpected exit; output={result.output} errors={result.errors}"
    assert any("RUNTIME_PROBE_OK" in line for line in result.output)
    assert result.errors == []
