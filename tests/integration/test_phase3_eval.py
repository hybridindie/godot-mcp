#!/usr/bin/env python3
"""Integration tests for Phase 3 eval tools.

- instruction_staleness: verify static analysis correctness
- transition_test: verify data structures and toolset lookup
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

    print(f"  Static analysis: {result['python_total']} Python, {result['gdscript_total']} GDScript, {result['shared']} shared")


def test_transition_scenarios() -> None:
    """TRANSITION_SCENARIOS should be well-formed."""
    from evals.transition_test import TRANSITION_SCENARIOS

    assert len(TRANSITION_SCENARIOS) > 0, "No transition scenarios defined"

    for from_t, to_t, prompt in TRANSITION_SCENARIOS:
        assert from_t, "Empty from_toolset"
        assert to_t, "Empty to_toolset"
        assert prompt, "Empty task prompt"
        assert from_t != to_t, f"Same toolset in transition: {from_t}"

    print(f"  Transition scenarios: {len(TRANSITION_SCENARIOS)} defined")


if __name__ == "__main__":
    test_static_analysis()
    test_transition_scenarios()
    print("\n✅ All Phase 3 integration tests passed")
