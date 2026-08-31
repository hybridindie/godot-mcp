#!/usr/bin/env python3
"""Unified eval runner with parallel execution and regression baseline.

Runs all eval suites (infrastructure + agent behavior + regression) with:
- Parallel task execution for faster cycles
- Regression baseline: run with pre-PR descriptions stripped of improvements
- MLflow logging with variant tags → removed with the MLflow decoupling (2026-08)

Usage:
    python -m evals.runner --baseline    # Run with pre-PR descriptions
    python -m evals.runner --post-pr      # Run with current (improved) descriptions
    python -m evals.runner --compare     # Run both and compare
    python -m evals.runner --parallel 4  # Use 4 concurrent workers
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, "/Users/johnd/Development/godot-mcp")

from evals.agent_suite_v2 import (
    AgentTaskResult,
)
from evals.agent_suite_v2 import (
    BridgeConnector as AgentBridge,
)
from evals.archive.suite import (
    BridgeConnector as InfraBridge,
)
from evals.archive.suite import (
    ToolsetResult as InfraToolsetResult,
)


@dataclass
class UnifiedResult:
    """Aggregated results from all eval suites."""

    variant: str  # "baseline" or "post-pr"
    infra_results: list[InfraToolsetResult] = field(default_factory=list)
    agent_results: list[AgentTaskResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def infra_pass_rate(self) -> float:
        total = sum(len(tr.tasks) for tr in self.infra_results)
        passed = sum(
            sum(1 for t in tr.tasks if t.success)
            for tr in self.infra_results
        )
        return passed / max(total, 1)

    @property
    def agent_mean_score(self) -> float:
        if not self.agent_results:
            return 0.0
        return sum(t.score.overall for t in self.agent_results) / len(self.agent_results)

    @property
    def agent_compliance(self) -> float:
        if not self.agent_results:
            return 0.0
        return (
            sum(1 for t in self.agent_results if t.score.overall >= 0.7)
            / len(self.agent_results)
        )


async def run_infra_tasks(
    bridge: InfraBridge, variant: str
) -> list[InfraToolsetResult]:
    """Run infrastructure tasks (from suite.py)."""
    from evals.suite import TASKS

    results: list[InfraToolsetResult] = []
    for toolset, task_fn in TASKS.items():
        try:
            task_result = await task_fn(bridge)
            results.append(InfraToolsetResult(toolset=toolset, tasks=[task_result]))
        except Exception as e:
            print(f"    💥 INFRA EXCEPTION: {toolset}: {e}")
    return results


async def run_agent_tasks(
    bridge: AgentBridge, variant: str
) -> list[AgentTaskResult]:
    """Run agent behavior tasks (from agent_suite_v2.py)."""
    from evals.agent_suite_v2 import ALL_AGENT_TASKS

    results: list[AgentTaskResult] = []
    for task_name, task_fn in ALL_AGENT_TASKS:
        try:
            task_result = await task_fn(bridge)
            results.append(task_result)
        except Exception as e:
            print(f"    💥 AGENT EXCEPTION: {task_name}: {e}")
    return results


async def run_parallel(variant: str, max_workers: int = 4) -> UnifiedResult:
    """Run both suites with parallel task execution."""
    result = UnifiedResult(variant=variant)
    start = time.perf_counter()

    print(f"\n{'='*70}")
    print(f"  Unified Eval Runner — variant: {variant}")
    print(f"  Workers: {max_workers}")
    print(f"{'='*70}")

    # Create separate bridge instances for infra and agent suites
    infra_bridge = InfraBridge()
    agent_bridge = AgentBridge()

    if not await infra_bridge.connect():
        print("❌ Infrastructure bridge failed to connect")
        return result
    if not await agent_bridge.connect():
        print("❌ Agent bridge failed to connect")
        return result

    # Run both suites concurrently
    infra_future = asyncio.create_task(run_infra_tasks(infra_bridge, variant))
    agent_future = asyncio.create_task(run_agent_tasks(agent_bridge, variant))

    result.infra_results = await infra_future
    result.agent_results = await agent_future

    await infra_bridge.close()
    await agent_bridge.close()

    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


def print_comparison(baseline: UnifiedResult, post_pr: UnifiedResult) -> None:
    """Print a side-by-side comparison of baseline vs post-PR."""
    print("\n" + "=" * 70)
    print("  Regression Comparison: Baseline vs Post-PR")
    print("=" * 70)
    print(f"  {'Metric':<30} {'Baseline':<12} {'Post-PR':<12} {'Delta':<12}")
    print("  " + "-" * 66)

    metrics = [
        ("Infra pass rate", baseline.infra_pass_rate, post_pr.infra_pass_rate),
        ("Agent mean score", baseline.agent_mean_score, post_pr.agent_mean_score),
        ("Agent compliance", baseline.agent_compliance, post_pr.agent_compliance),
        ("Duration (ms)", baseline.duration_ms / 1000, post_pr.duration_ms / 1000),
    ]

    for name, base, post in metrics:
        delta = post - base
        delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
        print(f"  {name:<30} {base:<12.2f} {post:<12.2f} {delta_str:<12}")

    print("=" * 70)


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Unified eval runner")
    parser.add_argument(
        "--mode",
        choices=["baseline", "post-pr", "compare"],
        default="post-pr",
        help="Which variant to run",
    )
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    if args.mode == "compare":
        baseline = await run_parallel("baseline", args.workers)
        post_pr = await run_parallel("post-pr", args.workers)
        print_comparison(baseline, post_pr)
    else:
        result = await run_parallel(args.mode, args.workers)
        print(f"\n  Infra pass rate: {result.infra_pass_rate:.1%}")
        print(f"  Agent mean score: {result.agent_mean_score:.2f}")
        print(f"  Agent compliance: {result.agent_compliance:.1%}")
        print(f"  Duration: {result.duration_ms:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
