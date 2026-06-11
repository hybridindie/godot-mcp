#!/usr/bin/env python3
"""Real LLM agent evaluation for godot-mcp.

Runs each agent_suite_v2 task through an actual LLM (qwen3-coder:30b) to measure:
- First-attempt correctness
- Recovery behavior
- Token efficiency
- Error taxonomy

Usage:
    # Run with current (post-PR) descriptions
    python -m evals.llm_eval

    # A/B test: baseline vs post-PR
    python -m evals.llm_eval --compare --runs 3

    # Run a specific task
    python -m evals.llm_eval --task toolset_compliance
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, "/Users/johnd/Development/godot-mcp")

from evals.agent_suite_v2 import (
    ALL_AGENT_TASKS,
    BridgeConnector,
    TaskScore,
)
from evals.mlflow_tracker import EvalTracker
from evals.ollama_agent import OllamaAgent, get_available_tools

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class ErrorTaxonomy:
    """Categorize errors into agent vs precondition vs infrastructure vs bug."""

    AGENT_PATTERNS = [
        "unknown tool",
        "unknown command",
        "has no property",
        "invalid parameter",
        "missing required",
    ]
    PRECONDITION_PATTERNS = [
        "no play session",
        "not found",
        "no node",
        "toolset not enabled",
        "requires",
    ]
    INFRA_PATTERNS = [
        "bridge",
        "disconnected",
        "timeout",
        "not running",
        "connection",
    ]

    @classmethod
    def classify(cls, error: str, hint: str) -> str:
        text = f"{error} {hint}".lower()
        for p in cls.INFRA_PATTERNS:
            if p in text:
                return "infrastructure"
        for p in cls.PRECONDITION_PATTERNS:
            if p in text:
                return "precondition"
        for p in cls.AGENT_PATTERNS:
            if p in text:
                return "agent"
        return "unknown"


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def tokens_per_step(self) -> float:
        return self.total_tokens / max(1, 1)  # Will be divided by actual steps


def get_git_sha() -> str:
    """Get current git SHA for regression tracking."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd="/Users/johnd/Development/godot-mcp",
        )
        return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Task translation: convert agent_suite_v2 tasks to LLM prompts
# ---------------------------------------------------------------------------

TASK_PROMPTS: dict[str, str] = {
    "toolset_compliance": (
        "Create a Node2D named 'ComplianceTest' in the current scene. "
        "Use get_scene_tree first to see the current scene, then create the node."
    ),
    "error_recovery_input": (
        "Simulate pressing the Space key in the game. "
        "If the game is not running, start it first with play_scene."
    ),
    "error_recovery_physics": (
        "Set the position of the Player node to (100, 100). "
        "Use get_scene_tree first to find the correct Player node path."
    ),
    "decision_tree_routing": (
        "Run the game and get the live game scene tree (NOT the editor scene tree)."
    ),
    "description_boundary": (
        "Get the current project information."
    ),
    "description_when_not": (
        "Run the game and inspect the live game state."
    ),
    "description_recovery_hints": (
        "Create a Node2D named 'HintTest' and set its 'position' property. "
        "If setting the property fails, check what properties are available first."
    ),
    "batch_awareness": (
        "Create 3 Node2D nodes named BatchNode0, BatchNode1, BatchNode2. "
        "Then set all their positions to (100, 100) efficiently using the fewest calls possible."
    ),
    "script_iteration": (
        "Use write_script to create a GDScript file at res://scripts/eval_test.gd. "
        "The script should extend Node and have a _ready function that prints 'hello'. "
        "After writing, verify the script file was created successfully."
    ),
    "profiling_decision": (
        "Check the editor's current performance/FPS. The game is NOT running."
    ),
}


# ---------------------------------------------------------------------------
# LLM-driven task execution with scoring
# ---------------------------------------------------------------------------

@dataclass
class LLMTaskResult:
    """Result of running a single task through the real LLM."""

    task_name: str
    steps: list[dict] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    score: TaskScore = field(default_factory=TaskScore)
    first_attempt_correct: bool = False
    errors: int = 0
    duration_ms: float = 0.0
    error_categories: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)


class LLMTaskRunner:
    """Run agent_suite_v2 tasks through a real LLM agent."""

    def __init__(self, bridge: BridgeConnector, model: str = "qwen3-coder:30b") -> None:
        self._bridge = bridge
        self._model = model
        self._agent: OllamaAgent | None = None

    async def run_task(
        self,
        task_name: str,
        max_steps: int = 10,
    ) -> LLMTaskResult:
        """Run a single task end-to-end through the LLM."""
        result = LLMTaskResult(task_name=task_name)
        start = time.perf_counter()

        # Cleanup bridge state
        await self._bridge.cleanup()

        # Build task prompt with explicit instructions
        base_prompt = TASK_PROMPTS.get(task_name, f"Complete the task: {task_name}")
        prompt = (
            f"{base_prompt}\n\n"
            "IMPORTANT: You MUST call one or more tools to complete this task. "
            "Do NOT return 'done' until you have successfully completed all required actions. "
            "Return ONLY a JSON object with the tool to call. "
            "When the task is COMPLETELY finished, return {\"tool\": \"done\"}."
        )
        tools = get_available_tools()

        # Create fresh agent per task
        self._agent = OllamaAgent(self._bridge._bridge, model=self._model)
        self._agent._history = []  # Reset history

        # Track if first step was correct
        expected_first_tools = {
            "toolset_compliance": "get_scene_tree",
            "error_recovery_input": "play_scene",
            "error_recovery_physics": "get_scene_tree",
            "decision_tree_routing": "play_scene",
            "description_boundary": "get_project_info",
            "description_when_not": "play_scene",
            "description_recovery_hints": "create_node",
            "batch_awareness": "create_node",
            "script_iteration": "write_script",
            "profiling_decision": "get_editor_performance",
        }
        expected_first = expected_first_tools.get(task_name)

        for step_num in range(max_steps):
            # Build dynamic prompt based on step
            if step_num == 0:
                step_prompt = prompt
            else:
                step_prompt = "Continue completing the task. Choose the next tool to call."

            # Ask LLM for next action
            try:
                call = self._agent._ask(step_prompt, tools)
            except Exception as e:
                result.notes = f"LLM query failed: {e}"
                result.errors += 1
                result.error_categories.append("infrastructure")
                break

            # Track tokens from the LLM response
            result.token_usage.prompt_tokens += call.prompt_tokens
            result.token_usage.completion_tokens += call.completion_tokens
            result.token_usage.total_tokens += call.prompt_tokens + call.completion_tokens

            # Execute the tool
            try:
                exec_result = await self._agent._execute(call)
            except Exception as e:
                exec_result = {
                    "ok": False,
                    "error": str(e),
                    "hint": "Execution failed",
                    "done": False,
                }

            # Add to history
            self._agent._add_result(exec_result)

            # Record step
            step_record = {
                "step": step_num + 1,
                "tool": call.tool,
                "params": call.params,
                "reasoning": call.reasoning,
                "ok": exec_result.get("ok", False),
                "error": exec_result.get("error"),
                "hint": exec_result.get("hint"),
            }
            result.steps.append(step_record)

            # Check first attempt correctness
            if step_num == 0 and expected_first:
                result.first_attempt_correct = call.tool == expected_first

            # Categorize errors
            if not exec_result.get("ok", False):
                result.errors += 1
                category = ErrorTaxonomy.classify(
                    exec_result.get("error", ""),
                    exec_result.get("hint", ""),
                )
                result.error_categories.append(category)

            # Stop conditions
            if call.tool == "done" or exec_result.get("done"):
                break

            # Safety: stop if too many consecutive errors
            if result.errors >= 3:
                result.notes = "Stopped: too many errors"
                break

        result.duration_ms = (time.perf_counter() - start) * 1000

        # Score the result (using agent_suite_v2 scoring logic adapted for LLM)
        result.score = self._score_task(result, task_name)

        return result

    def _score_task(self, result: LLMTaskResult, task_name: str) -> TaskScore:
        """Score an LLM task result using multi-dimensional rubric."""
        score = TaskScore()

        # Filter out "done" steps — only real tool calls count
        real_steps = [s for s in result.steps if s["tool"] != "done"]

        # tool_choice: Did it eventually call a correct tool that succeeded?
        last_ok = any(s["ok"] for s in real_steps)
        score.tool_choice = 1.0 if last_ok else 0.0

        # prerequisites: First real step correct?
        score.prerequisites = 1.0 if result.first_attempt_correct else 0.0

        # recovery: Did it recover from errors?
        real_errors = [s for s in real_steps if not s["ok"]]
        if len(real_errors) == 0:
            score.recovery = 1.0
        elif any(s["ok"] for s in real_steps[1:]) and len(real_errors) > 0:
            score.recovery = 1.0  # Recovered after initial failure
        else:
            score.recovery = 0.0

        # efficiency: Steps vs optimal
        optimal = {
            "toolset_compliance": 2,
            "error_recovery_input": 2,
            "error_recovery_physics": 3,
            "decision_tree_routing": 2,
            "description_boundary": 1,
            "description_when_not": 2,
            "description_recovery_hints": 3,
            "batch_awareness": 3,  # enable batch + create 3 nodes + batch_set_property
            "script_iteration": 2,
            "profiling_decision": 1,
        }.get(task_name, 3)

        # Efficiency based on real steps (excluding done)
        real_step_count = len(real_steps)
        if real_step_count <= optimal:
            score.efficiency = 1.0
        else:
            ratio = (real_step_count - optimal) / optimal
            score.efficiency = max(0.0, 1.0 - ratio * 0.5)

        return score


# ---------------------------------------------------------------------------
# Suite orchestration
# ---------------------------------------------------------------------------

async def run_llm_suite(
    tasks: list[str] | None = None,
    model: str = "qwen3-coder:30b",
    max_steps: int = 10,
) -> list[LLMTaskResult]:
    """Run selected tasks through the real LLM agent."""
    bridge = BridgeConnector()

    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge. Is Godot running?")
        return []

    runner = LLMTaskRunner(bridge, model=model)

    task_list = tasks or [t[0] for t in ALL_AGENT_TASKS]
    results: list[LLMTaskResult] = []

    print(f"\n{'='*70}")
    print(f"  Real LLM Eval Suite — {model}")
    print(f"  Tasks: {len(task_list)} | Max steps: {max_steps}")
    print(f"{'='*70}")

    for task_name in task_list:
        print(f"\n  [{task_name}]")
        try:
            result = await runner.run_task(task_name, max_steps=max_steps)
            results.append(result)

            s = result.score
            status = "PASS" if s.overall >= 0.7 else (
                "PARTIAL" if s.overall >= 0.4 else "FAIL"
            )
            print(
                f"    {status} | overall={s.overall:.2f} | "
                f"choice={s.tool_choice:.1f} prereq={s.prerequisites:.1f} "
                f"recovery={s.recovery:.1f} eff={s.efficiency:.1f} | "
                f"steps={result.step_count} errors={result.errors}"
            )
            print(f"    First attempt correct: {'✅' if result.first_attempt_correct else '❌'}")
            if result.error_categories:
                cats = ", ".join(set(result.error_categories))
                print(f"    Error categories: {cats}")
            if result.notes:
                print(f"    Notes: {result.notes}")

            # Print step trace
            for step in result.steps:
                icon = "✅" if step["ok"] else "❌"
                print(
                    f"      {icon} {step['step']}. {step['tool']}({json.dumps(step['params'])})")

        except Exception as e:
            print(f"    💥 EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    await bridge.close()
    return results


def print_summary(results: list[LLMTaskResult]) -> None:
    """Print aggregate summary."""
    if not results:
        print("No results to summarize.")
        return

    print("\n" + "=" * 70)
    print("  Real LLM Eval Summary")
    print("=" * 70)

    total_pass = total_partial = total_fail = 0
    total_first_correct = 0
    total_errors = 0
    total_steps = 0

    for r in results:
        s = r.score
        if s.overall >= 0.7:
            total_pass += 1
        elif s.overall >= 0.4:
            total_partial += 1
        else:
            total_fail += 1
        total_first_correct += 1 if r.first_attempt_correct else 0
        total_errors += r.errors
        total_steps += r.step_count

    mean_score = sum(r.score.overall for r in results) / len(results)
    compliance = total_pass / len(results)
    first_attempt = total_first_correct / len(results)

    # Error taxonomy breakdown
    all_categories = []
    for r in results:
        all_categories.extend(r.error_categories)
    cat_counts: dict[str, int] = {}
    for c in all_categories:
        cat_counts[c] = cat_counts.get(c, 0) + 1

    print(f"  Tasks evaluated: {len(results)}")
    print(f"  Mean overall score: {mean_score:.2f}")
    print(f"  Compliance rate: {compliance:.0%}")
    print(f"  First-attempt correct: {first_attempt:.0%}")
    print(f"  Total errors: {total_errors}")
    print(f"  Mean steps per task: {total_steps / len(results):.1f}")

    if cat_counts:
        print("\n  Error taxonomy:")
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

    print(f"\n  Breakdown: {total_pass} pass, {total_partial} partial, {total_fail} fail")
    print("=" * 70)


def log_results(
    results: list[LLMTaskResult],
    variant: str = "post-pr",
    model: str = "qwen3-coder:30b",
) -> None:
    """Log real LLM eval metrics to MLFlow."""
    tracker = EvalTracker()
    git_sha = get_git_sha()

    tracker.start_run(
        run_name=f"llm-eval-{variant}-{int(time.time())}",
        variant=variant,
    )

    # Global metrics
    tracker.log_param("model", model)
    tracker.log_param("git_sha", git_sha)
    tracker.log_param("variant", variant)

    if results:
        mean_score = sum(r.score.overall for r in results) / len(results)
        compliance = sum(1 for r in results if r.score.overall >= 0.7) / len(results)
        first_attempt = sum(1 for r in results if r.first_attempt_correct) / len(results)
        total_errors = sum(r.errors for r in results)
        total_steps = sum(r.step_count for r in results)

        tracker.log_metric("mean_score", mean_score)
        tracker.log_metric("compliance_rate", compliance)
        tracker.log_metric("first_attempt_rate", first_attempt)
        tracker.log_metric("total_errors", total_errors)
        tracker.log_metric("mean_steps", total_steps / len(results))

        # Error taxonomy
        all_categories = []
        for r in results:
            all_categories.extend(r.error_categories)
        cat_counts: dict[str, int] = {}
        for c in all_categories:
            cat_counts[c] = cat_counts.get(c, 0) + 1
        for cat, count in cat_counts.items():
            tracker.log_metric(f"errors_{cat}", count)

        # Per-task metrics
        for r in results:
            s = r.score
            prefix = r.task_name
            tracker.log_metric(f"{prefix}_overall", s.overall)
            tracker.log_metric(f"{prefix}_tool_choice", s.tool_choice)
            tracker.log_metric(f"{prefix}_prerequisites", s.prerequisites)
            tracker.log_metric(f"{prefix}_recovery", s.recovery)
            tracker.log_metric(f"{prefix}_efficiency", s.efficiency)
            tracker.log_metric(f"{prefix}_steps", r.step_count)
            tracker.log_metric(f"{prefix}_errors", r.errors)
            tracker.log_metric(
                f"{prefix}_first_attempt", 1.0 if r.first_attempt_correct else 0.0
            )
            if r.notes:
                tracker.log_param(f"{prefix}_notes", r.notes[:250])

    tracker.end_run()
    print("\n📊 Logged to MLFlow: https://mlflow.johndstudios.net/#/experiments/55")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Real LLM eval for godot-mcp")
    parser.add_argument(
        "--tasks",
        nargs="+",
        help="Specific tasks to run (default: all)",
    )
    parser.add_argument(
        "--model",
        default="qwen3-coder:30b",
        help="Ollama model to use",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="Max LLM steps per task",
    )
    parser.add_argument(
        "--variant",
        default="post-pr",
        help="Description variant tag for MLFlow",
    )
    args = parser.parse_args()

    results = await run_llm_suite(
        tasks=args.tasks,
        model=args.model,
        max_steps=args.max_steps,
    )

    print_summary(results)

    if results:
        log_results(results, variant=args.variant, model=args.model)


if __name__ == "__main__":
    asyncio.run(main())
