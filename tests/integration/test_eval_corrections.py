#!/usr/bin/env python3
"""Dynamic corrective-prompt tests (issue #149).

After a failed tool call, the agent injects a compact, high-attention
correction into the next user message so it stops repeating the same mistake.
The formatter and the injection are unit-testable without a live LLM/bridge.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.cloud_client import CloudAgent  # noqa: E402
from evals.correction import CORRECTION_LIMIT, format_correction  # noqa: E402
from evals.ollama_agent import OllamaAgent  # noqa: E402


def test_format_correction_includes_call_error_and_hint() -> None:
    msg = format_correction(
        "attach_script",
        {"node_path": "Background", "script_path": "res://background.gd"},
        "RESOURCE_NOT_FOUND",
        "The exact path is res://scripts/debugger_demo.gd.",
    )
    assert "attach_script" in msg
    assert "RESOURCE_NOT_FOUND" in msg
    assert "debugger_demo.gd" in msg
    assert "CORRECTION" in msg


def test_format_correction_capped() -> None:
    msg = format_correction("t", {"x": "y" * 500}, "ERR", "h" * 500)
    assert len(msg) <= CORRECTION_LIMIT


def test_format_correction_handles_missing_hint() -> None:
    msg = format_correction("play_scene", {}, "PRECONDITION_FAILED", None)
    assert "play_scene" in msg and "PRECONDITION_FAILED" in msg


def _failed() -> dict[str, object]:
    return {
        "ok": False,
        "error": "RESOURCE_NOT_FOUND",
        "hint": "Use res://scripts/debugger_demo.gd exactly.",
        "result": {},
    }


def test_ollama_injects_correction_on_failure() -> None:
    agent = OllamaAgent(bridge=None)  # type: ignore[arg-type]
    agent._last_tool = "attach_script"
    agent._last_params = {"script_path": "res://background.gd"}
    agent._add_result(_failed())
    content = agent._history[-1]["content"]
    assert "CORRECTION" in content and "attach_script" in content


def test_ollama_no_correction_on_success() -> None:
    agent = OllamaAgent(bridge=None)  # type: ignore[arg-type]
    agent._last_tool = "create_node"
    agent._last_params = {"name": "X"}
    agent._add_result({"ok": True, "result": {"node_path": "X"}})
    assert "CORRECTION" not in agent._history[-1]["content"]


def test_cloud_injects_correction_on_failure() -> None:
    agent = CloudAgent(bridge=None, provider="anthropic", api_key="test")
    agent._last_tool = "connect_signal"
    agent._last_params = {"signal_name": "ready"}
    agent._add_result(_failed())
    content = agent._history[-1]["content"]
    assert "CORRECTION" in content and "connect_signal" in content
