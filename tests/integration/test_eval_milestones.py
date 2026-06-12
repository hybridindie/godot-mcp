#!/usr/bin/env python3
"""Milestone-enforcement scoring tests (issue #150).

Milestones complement the end-state validators (#145): they verify that each
required sub-step actually happened, so an agent that does half a task and then
calls ``done()`` is capped rather than scored as a pass.

``_score_task`` reads only the result + module-level tables (not the bridge),
so it is unit-testable with a hand-built ``LLMTaskResult``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.llm_eval_v2 import (  # noqa: E402
    TASK_MILESTONES,
    LLMTaskResult,
    LLMTaskRunner,
)


def _runner() -> LLMTaskRunner:
    # _score_task never touches the bridge; a placeholder is fine.
    return LLMTaskRunner(bridge=None)  # type: ignore[arg-type]


def _result(task: str, steps: list[tuple[str, bool]]) -> LLMTaskResult:
    r = LLMTaskResult(task_name=task)
    r.steps = [{"tool": t, "ok": ok, "error": None} for t, ok in steps]
    r.first_attempt_correct = True
    return r


def test_milestones_defined_for_known_multistep_tasks() -> None:
    # Mirrors the prompt: create_node AND delete_node AND get_scene_tree.
    assert TASK_MILESTONES["mutate_delete_with_confirm"] == [
        "create_node",
        "delete_node",
        "get_scene_tree",
    ]
    assert "connect_signal" in TASK_MILESTONES["workflow_signal_and_test"]


def test_done_before_milestones_caps_score() -> None:
    # Created MutTest then called done — never deleted. Milestone unmet.
    runner = _runner()
    result = _result("mutate_delete_with_confirm", [("create_node", True), ("done", True)])
    score = runner._score_task(result, "mutate_delete_with_confirm")
    assert score.overall <= 0.3, f"half-task should cap at 0.3, got {score.overall}"
    assert "MILESTONE" in score.notes


def test_all_milestones_met_is_not_capped() -> None:
    runner = _runner()
    result = _result(
        "mutate_delete_with_confirm",
        [("create_node", True), ("delete_node", True), ("get_scene_tree", True), ("done", True)],
    )
    score = runner._score_task(result, "mutate_delete_with_confirm")
    assert score.overall > 0.3, f"completed task wrongly milestone-capped: {score.overall}"


def test_milestone_requires_successful_call_not_just_attempt() -> None:
    # delete_node was called but FAILED — the sub-goal wasn't achieved.
    runner = _runner()
    result = _result(
        "mutate_delete_with_confirm",
        [("create_node", True), ("delete_node", False), ("done", True)],
    )
    score = runner._score_task(result, "mutate_delete_with_confirm")
    assert score.overall <= 0.3


def test_task_without_milestones_is_unaffected() -> None:
    runner = _runner()
    result = _result("profiling_fps", [("get_editor_performance", True), ("done", True)])
    score = runner._score_task(result, "profiling_fps")
    assert score.overall > 0.3
    assert "MILESTONE" not in score.notes
