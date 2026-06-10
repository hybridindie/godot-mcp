#!/usr/bin/env python3
"""Variant A/B testing framework for godot-mcp tool descriptions.

Swaps tool descriptions at runtime and measures impact on:
- Completion rate
- Mean steps per task
- First-attempt correctness
- Token efficiency

Usage:
    python -m evals.variant_ab_test --variant baseline --runs 5
    python -m evals.variant_ab_test --variant all --runs 3 --tasks batch_set_multiple
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, "/Users/johnd/Development/godot-mcp")

from evals.llm_eval_v2 import (
    BridgeConnector,
    LLMTaskResult,
    LLMTaskRunner,
)
from evals.llm_eval_v2 import (
    get_available_tools as _get_base_tools,
)
from evals.mlflow_tracker import EvalTracker

# ---------------------------------------------------------------------------
# Description variants
# ---------------------------------------------------------------------------

VARIANTS: dict[str, list[dict]] = {
    "baseline": [],  # Uses current tools from llm_eval_v2
    "concise": [],
    "structured": [],
    "agent_optimized": [],
}


def _make_concise(tools: list[dict]) -> list[dict]:
    """Strip descriptions to tool name + one-sentence purpose."""
    concise: list[dict] = []
    for t in tools:
        name = t["name"]
        # Map to ultra-short descriptions
        short = {
            "get_scene_tree": "Scene hierarchy.",
            "get_node_properties": "Node properties.",
            "create_node": "Add node.",
            "set_node_property": "Set property.",
            "delete_node": "Delete node. Needs confirm=true.",
            "rename_node": "Rename node.",
            "save_scene": "Save scene.",
            "connect_signal": "Connect signal.",
            "play_scene": "Run game.",
            "stop_scene": "Stop game.",
            "batch_set_property": "Batch set property.",
            "done": "Task done.",
        }.get(name, t["description"].split(".")[0] + ".")
        concise.append({"name": name, "description": short})
    return concise


def _make_structured(tools: list[dict]) -> list[dict]:
    """Add WHEN/WHEN-NOT/RETURNS sections."""
    structured: list[dict] = []
    for t in tools:
        name = t["name"]
        base = t["description"]
        when = ""
        when_not = ""
        returns = ""

        if name == "play_scene":
            when = "WHEN: You need to run the game."
            when_not = "WHEN-NOT: Game is already running."
            returns = "RETURNS: {running: true}"
        elif name == "create_node":
            when = "WHEN: Adding a new node to the scene."
            when_not = "WHEN-NOT: Node already exists."
            returns = "RETURNS: {node_path, created}"
        elif name == "set_node_property":
            when = "WHEN: Changing a node's property value."
            when_not = "WHEN-NOT: Property doesn't exist (use get_node_property_list first)."
            returns = "RETURNS: {node_path, property, value}"
        elif name == "connect_signal":
            when = "WHEN: Linking a signal to a handler method."
            when_not = "WHEN-NOT: Signal or method doesn't exist."
            returns = "RETURNS: {source_path, signal_name, target_path, method_name, connected}"

        if when:
            desc = f"{base}\n{when}\n{when_not}\n{returns}"
        else:
            desc = base
        structured.append({"name": name, "description": desc})
    return structured


def _make_agent_optimized(tools: list[dict]) -> list[dict]:
    """Add 'Call this when...' + recovery hints."""
    optimized: list[dict] = []
    for t in tools:
        name = t["name"]
        base = t["description"]
        hint = ""

        if name == "play_scene":
            hint = (
                "Call this BEFORE using get_game_scene_tree or simulate_key. "
                "If the game is already running, this call is safe to repeat."
            )
        elif name == "create_node":
            hint = (
                "Call this when the task requires adding a new object. "
                "Use parent_path='.' for root-level nodes."
            )
        elif name == "set_node_property":
            hint = (
                "Call this to mutate a node. "
                "IF THIS FAILS with 'no property', call get_node_property_list first."
            )
        elif name == "connect_signal":
            hint = (
                "Call this to wire signals. "
                "IF THIS FAILS, verify both nodes exist with get_scene_tree."
            )
        elif name == "batch_set_property":
            hint = (
                "Call this for bulk updates on 2+ nodes. "
                "More efficient than calling set_node_property in a loop."
            )

        if hint:
            desc = f"{base}\n{hint}"
        else:
            desc = base
        optimized.append({"name": name, "description": desc})
    return optimized


def get_tools_for_variant(variant: str) -> list[dict]:
    """Return tool descriptions for a specific variant."""
    base = _get_base_tools()
    if variant == "baseline":
        return base
    if variant == "concise":
        return _make_concise(base)
    if variant == "structured":
        return _make_structured(base)
    if variant == "agent_optimized":
        return _make_agent_optimized(base)
    raise ValueError(f"Unknown variant: {variant}")


# ---------------------------------------------------------------------------
# A/B test runner
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    variant: str
    task_name: str
    runs: list[LLMTaskResult] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        return sum(1 for r in self.runs if r.score.overall >= 0.7) / max(len(self.runs), 1)

    @property
    def mean_score(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.score.overall for r in self.runs) / len(self.runs)

    @property
    def mean_steps(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.step_count for r in self.runs) / len(self.runs)

    @property
    def first_attempt_rate(self) -> float:
        return sum(1 for r in self.runs if r.first_attempt_correct) / max(len(self.runs), 1)

    @property
    def mean_tokens(self) -> float:
        if not self.runs:
            return 0.0
        total = sum(
            r.token_usage.prompt_tokens + r.token_usage.completion_tokens
            for r in self.runs
        )
        return total / len(self.runs)


@dataclass
class ABTestResult:
    task_name: str
    baseline: VariantResult | None = None
    concise: VariantResult | None = None
    structured: VariantResult | None = None
    agent_optimized: VariantResult | None = None

    def all_variants(self) -> list[tuple[str, VariantResult | None]]:
        return [
            ("baseline", self.baseline),
            ("concise", self.concise),
            ("structured", self.structured),
            ("agent_optimized", self.agent_optimized),
        ]

    def winner(self) -> str:
        """Return the variant with highest mean score."""
        best = "baseline"
        best_score = self.baseline.mean_score if self.baseline else 0.0
        for name, result in self.all_variants():
            if result and result.mean_score > best_score:
                best = name
                best_score = result.mean_score
        return best


async def run_variant_task(
    bridge: BridgeConnector,
    task_name: str,
    variant: str,
    model: str = "qwen3-coder:30b",
    max_steps: int = 8,
) -> LLMTaskResult:
    """Run a single task with a specific variant."""
    variant_tools = get_tools_for_variant(variant)

    # Monkey-patch get_available_tools for this variant run
    import evals.llm_eval_v2 as llm_mod
    old_get_tools = llm_mod.get_available_tools
    llm_mod.get_available_tools = lambda: variant_tools

    runner = LLMTaskRunner(bridge, model=model)
    try:
        result = await runner.run_task(task_name, max_steps=max_steps)
    finally:
        llm_mod.get_available_tools = old_get_tools

    return result


async def run_ab_test(
    task_names: list[str],
    variants: list[str],
    runs_per_variant: int = 3,
    model: str = "qwen3-coder:30b",
    max_steps: int = 8,
) -> list[ABTestResult]:
    """Run A/B test across tasks and variants."""
    bridge = BridgeConnector()
    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge.")
        return []

    results: list[ABTestResult] = []

    for task_name in task_names:
        print(f"\n{'='*60}")
        print(f"  Task: {task_name}")
        print(f"{'='*60}")

        ab_result = ABTestResult(task_name=task_name)

        for variant in variants:
            print(f"\n  Variant: {variant}")
            variant_result = VariantResult(variant=variant, task_name=task_name)

            for run in range(runs_per_variant):
                print(f"    Run {run + 1}/{runs_per_variant}...", end=" ", flush=True)
                result = await run_variant_task(
                    bridge, task_name, variant, model, max_steps
                )
                variant_result.runs.append(result)
                status = "PASS" if result.score.overall >= 0.7 else "PARTIAL"
                print(f"{status} score={result.score.overall:.2f} steps={result.step_count}")

            # Summary for this variant
            print(
                f"    Summary: completion={variant_result.completion_rate:.0%} "
                f"mean={variant_result.mean_score:.2f} "
                f"steps={variant_result.mean_steps:.1f} "
                f"first={variant_result.first_attempt_rate:.0%} "
                f"tokens={variant_result.mean_tokens:.0f}"
            )

            if variant == "baseline":
                ab_result.baseline = variant_result
            elif variant == "concise":
                ab_result.concise = variant_result
            elif variant == "structured":
                ab_result.structured = variant_result
            elif variant == "agent_optimized":
                ab_result.agent_optimized = variant_result

        # Task-level winner
        winner = ab_result.winner()
        print(f"\n  🏆 Winner for {task_name}: {winner}")

        results.append(ab_result)

    await bridge.close()
    return results


# ---------------------------------------------------------------------------
# Statistical comparison
# ---------------------------------------------------------------------------

def compute_deltas(baseline: VariantResult, other: VariantResult) -> dict[str, float]:
    """Compute deltas between baseline and another variant."""
    return {
        "completion_delta": other.completion_rate - baseline.completion_rate,
        "score_delta": other.mean_score - baseline.mean_score,
        "steps_delta": other.mean_steps - baseline.mean_steps,
        "first_attempt_delta": other.first_attempt_rate - baseline.first_attempt_rate,
        "token_delta": other.mean_tokens - baseline.mean_tokens,
    }


def print_comparison(results: list[ABTestResult]) -> None:
    """Print A/B comparison table."""
    print("\n" + "=" * 80)
    print("  A/B Test Comparison")
    print("=" * 80)

    for ab in results:
        if not ab.baseline:
            continue

        print(f"\n  Task: {ab.task_name}")
        print(
            f"  {'Variant':<18} {'Completion':<12} {'Mean Score':<12} "
            f"{'Steps':<8} {'First-Att':<10} {'Tokens':<10}"
        )
        print("  " + "-" * 70)

        for name, result in ab.all_variants():
            if not result:
                continue
            marker = " 🏆" if name == ab.winner() else ""
            print(
                f"  {name:<18} {result.completion_rate:<12.0%} "
                f"{result.mean_score:<12.2f} {result.mean_steps:<8.1f} "
                f"{result.first_attempt_rate:<10.0%} {result.mean_tokens:<10.0f}{marker}"
            )

        # Deltas vs baseline
        print("\n  Deltas vs baseline:")
        for name, result in ab.all_variants():
            if not result or name == "baseline":
                continue
            deltas = compute_deltas(ab.baseline, result)
            print(
                f"    {name:<16} completion={deltas['completion_delta']:+.0%} "
                f"score={deltas['score_delta']:+.2f} "
                f"steps={deltas['steps_delta']:+.1f} "
                f"first={deltas['first_attempt_delta']:+.0%} "
                f"tokens={deltas['token_delta']:+.0f}"
            )

    print("=" * 80)


# ---------------------------------------------------------------------------
# MLFlow logging
# ---------------------------------------------------------------------------

def log_ab_results(results: list[ABTestResult], model: str = "qwen3-coder:30b") -> None:
    """Log A/B test results to MLFlow."""
    tracker = EvalTracker()

    for ab in results:
        if not ab.baseline:
            continue

        tracker.start_run(
            run_name=f"ab-test-{ab.task_name}-{int(time.time())}",
            variant="ab-comparison",
        )
        tracker.log_param("model", model)
        tracker.log_param("task", ab.task_name)
        tracker.log_param("runs_per_variant", len(ab.baseline.runs))

        for name, result in ab.all_variants():
            if not result:
                continue
            prefix = name
            tracker.log_metric(f"{prefix}_completion", result.completion_rate)
            tracker.log_metric(f"{prefix}_mean_score", result.mean_score)
            tracker.log_metric(f"{prefix}_mean_steps", result.mean_steps)
            tracker.log_metric(f"{prefix}_first_attempt", result.first_attempt_rate)
            tracker.log_metric(f"{prefix}_mean_tokens", result.mean_tokens)

        # Deltas
        for name, result in ab.all_variants():
            if not result or name == "baseline":
                continue
            deltas = compute_deltas(ab.baseline, result)
            prefix = f"delta_{name}"
            for key, value in deltas.items():
                tracker.log_metric(f"{prefix}_{key}", value)

        tracker.log_param("winner", ab.winner())
        tracker.end_run()

    print("\n📊 Logged to MLFlow: https://mlflow.johndstudios.net/#/experiments/55")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="A/B test tool descriptions")
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=["batch_set_multiple", "signal_connect_ready", "mutate_rename"],
        help="Tasks to evaluate",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["baseline", "concise", "structured", "agent_optimized"],
        help="Variants to compare",
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per variant")
    parser.add_argument("--model", default="qwen3-coder:30b")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    results = await run_ab_test(
        task_names=args.tasks,
        variants=args.variants,
        runs_per_variant=args.runs,
        model=args.model,
        max_steps=args.max_steps,
    )

    print_comparison(results)
    log_ab_results(results, model=args.model)


if __name__ == "__main__":
    asyncio.run(main())
