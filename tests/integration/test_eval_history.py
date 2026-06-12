#!/usr/bin/env python3
"""History-compression tests (issue #148).

After a configurable number of steps the agent sends a compact summary of the
older history instead of every full tool result, to curb token bloat and the
480b HTTP timeouts. The summary is template-built (no LLM call) and the raw
history is kept internally. Pure functions + the agent view are unit-testable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.history import (  # noqa: E402
    COMPRESSION_THRESHOLD,
    compress_history,
    summarize_history,
)
from evals.ollama_agent import OllamaAgent  # noqa: E402
from evals.profiler import ToolProfiler  # noqa: E402


def _call(tool: str, **params: object) -> dict[str, str]:
    return {"role": "assistant", "content": json.dumps({"tool": tool, "params": params})}


def _result(ok: bool, error: str | None = None, hint: str | None = None) -> dict[str, str]:
    body: dict[str, object] = {"ok": ok, "error": error, "hint": hint, "result_keys": []}
    return {"role": "user", "content": "Tool result: " + json.dumps(body)}


def _history(n: int) -> list[dict[str, str]]:
    h: list[dict[str, str]] = []
    for i in range(n):
        h.append(_call("create_node", name=f"N{i}"))
        h.append(_result(True))
    return h


def test_short_history_is_unchanged() -> None:
    h = _history(COMPRESSION_THRESHOLD)
    assert compress_history(h, COMPRESSION_THRESHOLD) == h


def test_long_history_is_compressed() -> None:
    h = _history(COMPRESSION_THRESHOLD + 3)
    out = compress_history(h, COMPRESSION_THRESHOLD)
    assert len(out) < len(h)
    assert out[0]["role"] == "user"
    assert "Progress summary" in out[0]["content"]
    # The most recent step's call survives verbatim.
    assert out[-2:] == h[-2:]


def test_summary_marks_success_and_failure_with_hint() -> None:
    msgs = [
        _call("create_node", name="MutTest"),
        _result(True),
        _call("attach_script", script_path="res://background.gd"),
        _result(False, "RESOURCE_NOT_FOUND", "Use res://scripts/debugger_demo.gd."),
    ]
    summary = summarize_history(msgs)
    assert "create_node" in summary
    assert "attach_script" in summary and "RESOURCE_NOT_FOUND" in summary
    assert "debugger_demo.gd" in summary


def test_profiler_tracks_compression_savings() -> None:
    p = ToolProfiler()
    assert p.compression_savings()["compressions"] == 0
    p.record_compression(before_chars=1000, after_chars=400)
    s = p.compression_savings()
    assert s["compressions"] == 1
    assert s["chars_saved"] == 600
    p.reset()
    assert p.compression_savings()["compressions"] == 0


def test_agent_history_view_compresses_and_records() -> None:
    agent = OllamaAgent(bridge=None)  # type: ignore[arg-type]
    agent._history = _history(COMPRESSION_THRESHOLD + 2)
    view = agent._history_view()
    assert len(view) < len(agent._history)  # raw history untouched
    assert agent._last_compression is not None
    assert agent._last_compression["after_chars"] < agent._last_compression["before_chars"]


def test_agent_history_view_noop_when_short() -> None:
    agent = OllamaAgent(bridge=None)  # type: ignore[arg-type]
    agent._history = _history(2)
    view = agent._history_view()
    assert view == agent._history
    assert agent._last_compression is None
