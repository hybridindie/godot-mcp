#!/usr/bin/env python3
"""Integration tests for the evals/ remnant: server self-analysis.

- instruction_staleness: verify static analysis correctness

The agent-facing harness (transition_test, llm_eval_v2, agents) moved to
godot-agents (``godot_agent_harness``, godot-agents#481); its tests moved
with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.instruction_staleness import StaticAnalyzer


def test_static_analysis() -> None:
    """StaticAnalyzer should find tools on both sides."""
    repo_root = Path(__file__).resolve().parents[2]
    analyzer = StaticAnalyzer(repo_root)

    # Both sides should have non-zero tools
    assert len(analyzer.python_tools) > 0, "No Python tools found"
    assert len(analyzer.gdscript_tools) > 0, "No GDScript tools found"

    # There should be significant overlap
    py_names = {t.name for t in analyzer.python_tools}
    gd_names = {t.name for t in analyzer.gdscript_tools}
    shared = py_names & gd_names
    assert len(shared) > 50, f"Too few shared tools: {len(shared)}"

    # Comparison should report totals
    result = analyzer.compare()
    assert result["shared"] == len(shared)
    assert result["python_total"] == len(py_names)
    assert result["gdscript_total"] == len(gd_names)

    msg = (
        f"  Static analysis: {result['python_total']} Python, "
        f"{result['gdscript_total']} GDScript, {result['shared']} shared"
    )
    print(msg)


if __name__ == "__main__":
    test_static_analysis()
    print("\n✅ Phase 3 integration tests passed")
