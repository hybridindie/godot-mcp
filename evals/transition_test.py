#!/usr/bin/env python3
"""Toolset Transition Cost Measurement (Gap Analysis #10).

Measures the friction when an agent switches between toolsets:
1. **enable_toolset latency**: Time to enable each toolset category
2. **context-switch steps**: Extra steps needed after enabling a new toolset
3. **forgetting rate**: Does the agent re-enable already-enabled toolsets?

Usage:
    python -m evals.transition_test --model qwen3-coder:30b
    python -m evals.transition_test --max-steps 15
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field

# Eval imports
from evals.agent_suite_v2 import BridgeConnector
from evals.mlflow_tracker import EvalTracker
from evals.ollama_agent import OllamaAgent

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TransitionResult:
    """Result of a single transition test."""

    from_toolset: str
    to_toolset: str
    enable_latency_ms: float = 0.0
    enable_ok: bool = False
    enable_hint: str = ""
    steps_to_first_success: int = 0
    first_tool_correct: bool = False
    total_tokens: int = 0
    notes: str = ""


@dataclass
class TransitionSuiteResult:
    """Aggregated transition test results."""

    transitions: list[TransitionResult] = field(default_factory=list)

    @property
    def mean_enable_latency_ms(self) -> float:
        latencies = [t.enable_latency_ms for t in self.transitions if t.enable_ok]
        return round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    @property
    def success_rate(self) -> float:
        if not self.transitions:
            return 0.0
        ok = sum(1 for t in self.transitions if t.enable_ok)
        return round(ok / len(self.transitions), 2)

    @property
    def mean_steps(self) -> float:
        steps = [t.steps_to_first_success for t in self.transitions if t.steps_to_first_success > 0]
        return round(sum(steps) / len(steps), 2) if steps else 0.0


# ---------------------------------------------------------------------------
# Toolset transition scenarios
# ---------------------------------------------------------------------------

TRANSITION_SCENARIOS: list[tuple[str, str, str]] = [
    # (from_toolset, to_toolset, task_prompt)
    (
        "scene_edit",
        "runtime",
        "Run the game and get the live scene tree. Then stop the game.",
    ),
    (
        "runtime",
        "scene_edit",
        "Create a Node2D named 'SwitchTest' in the editor.",
    ),
    (
        "scene_edit",
        "scripts",
        "Write a script to res://scripts/transition_test.gd and attach it to the SwitchTest node.",
    ),
    (
        "scripts",
        "physics",
        "Set up a RigidBody2D named 'PhysicsTest' with gravity scale 0.5.",
    ),
    (
        "physics",
        "input",
        "Simulate pressing the Space key in the game.",
    ),
]


# ---------------------------------------------------------------------------
# Transition runner
# ---------------------------------------------------------------------------


async def run_transition(
    bridge: BridgeConnector,
    from_toolset: str,
    to_toolset: str,
    task_prompt: str,
    model: str = "qwen3-coder:30b",
    max_steps: int = 10,
) -> TransitionResult:
    """Run a single transition scenario and measure costs."""
    result = TransitionResult(from_toolset=from_toolset, to_toolset=to_toolset)

    # Step 1: Ensure from_toolset is enabled
    await bridge.call("cmd_enable_toolset", {"category": from_toolset})

    # Step 2: Measure enable_toolset latency for to_toolset
    start = time.perf_counter()
    enable_resp = await bridge.call(
        "cmd_enable_toolset", {"category": to_toolset}
    )
    result.enable_latency_ms = (time.perf_counter() - start) * 1000
    result.enable_ok = enable_resp.get("ok", False)
    result.enable_hint = enable_resp.get("hint", "")

    if not result.enable_ok:
        result.notes = f"enable_toolset failed: {result.enable_hint}"
        return result

    # Step 3: Give the LLM the task and see how many steps until first success
    agent = OllamaAgent(bridge._bridge, model=model)
    agent._history = []

    tools = _get_tools_for_toolset(to_toolset)

    for step_num in range(max_steps):
        prompt = task_prompt if step_num == 0 else "Continue the task."
        try:
            call = agent._ask(prompt, tools)
        except Exception as e:
            result.notes = f"LLM query failed: {e}"
            break

        result.total_tokens += call.prompt_tokens + call.completion_tokens

        try:
            exec_result = await agent._execute(call)
        except Exception as e:
            exec_result = {"ok": False, "error": str(e)}

        agent._add_result(exec_result)

        if exec_result.get("ok", False) and call.tool != "done":
            result.steps_to_first_success = step_num + 1
            result.first_tool_correct = step_num == 0
            break

        # Check for re-enabling already-enabled toolset (forgetting)
        if call.tool == "enable_toolset":
            params = call.params or {}
            if params.get("category") == from_toolset:
                result.notes += f"Agent re-enabled '{from_toolset}' (forgetting). "
    else:
        result.notes += f"Did not succeed within {max_steps} steps. "

    return result


def _get_tools_for_toolset(toolset: str) -> list[dict[str, str]]:
    """Return a minimal tool list for the given toolset category."""
    toolsets: dict[str, list[str]] = {
        "scene_edit": ["create_node", "delete_node", "set_node_property", "get_scene_tree", "done"],
        "runtime": ["play_scene", "stop_scene", "get_game_scene_tree", "done"],
        "scripts": ["write_script", "attach_script", "read_script", "done"],
        "physics": ["setup_physics_body", "get_scene_tree", "done"],
        "input": ["simulate_key", "play_scene", "stop_scene", "done"],
    }
    names = toolsets.get(toolset, [])
    return [{"name": n, "description": ""} for n in names]


# ---------------------------------------------------------------------------
# Suite orchestration
# ---------------------------------------------------------------------------


async def run_suite(
    model: str = "qwen3-coder:30b",
    max_steps: int = 10,
) -> TransitionSuiteResult:
    bridge = BridgeConnector()
    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge")
        return TransitionSuiteResult()

    suite = TransitionSuiteResult()
    for from_t, to_t, prompt in TRANSITION_SCENARIOS:
        print(f"\n  Testing {from_t} → {to_t}...")
        result = await run_transition(
            bridge, from_t, to_t, prompt, model=model, max_steps=max_steps
        )
        suite.transitions.append(result)
        status = "✅" if result.enable_ok else "❌"
        print(
            f"    {status} enable={result.enable_latency_ms:.1f}ms "
            f"steps={result.steps_to_first_success} "
            f"tokens={result.total_tokens}"
        )

    await bridge.cleanup()
    await bridge.close()
    return suite


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(result: TransitionSuiteResult, model: str) -> None:
    print("\n" + "=" * 60)
    print("  Toolset Transition Cost Report")
    print("=" * 60)
    print(f"\n  Model: {model}")
    print(f"  Transitions tested: {len(result.transitions)}")
    print(f"  Success rate: {result.success_rate * 100:.0f}%")
    print(f"  Mean enable latency: {result.mean_enable_latency_ms}ms")
    print(f"  Mean steps to first success: {result.mean_steps}")
    print()
    for t in result.transitions:
        status = "✅" if t.enable_ok else "❌"
        print(f"  {status} {t.from_toolset:12} → {t.to_toolset:12}  "
              f"enable={t.enable_latency_ms:.1f}ms  "
              f"steps={t.steps_to_first_success}  "
              f"tokens={t.total_tokens}")
        if t.notes:
            print(f"      {t.notes}")
    print("=" * 60)


async def log_to_mlflow(result: TransitionSuiteResult, model: str) -> None:
    tracker = EvalTracker()
    tracker.start_run(run_name=f"transition-cost-{model}")
    tracker.log_param("eval_type", "transition_cost")
    tracker.log_param("model", model)
    tracker.log_metric("success_rate", result.success_rate)
    tracker.log_metric("mean_enable_latency_ms", result.mean_enable_latency_ms)
    tracker.log_metric("mean_steps", result.mean_steps)
    for i, t in enumerate(result.transitions):
        prefix = f"t{i}"
        tracker.log_param(f"{prefix}_from", t.from_toolset)
        tracker.log_param(f"{prefix}_to", t.to_toolset)
        tracker.log_metric(f"{prefix}_enable_ms", round(t.enable_latency_ms, 2))
        tracker.log_metric(f"{prefix}_steps", t.steps_to_first_success)
        tracker.log_metric(f"{prefix}_tokens", t.total_tokens)
    tracker.end_run()
    print("\n📊 Logged to MLFlow: https://mlflow.johndstudios.net/#/experiments/55")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="Toolset transition cost measurement")
    parser.add_argument("--model", default="qwen3-coder:30b", help="Ollama model")
    parser.add_argument("--max-steps", type=int, default=10, help="Max steps per transition")
    parser.add_argument("--log", action="store_true", help="Log to MLFlow")
    args = parser.parse_args()

    result = await run_suite(model=args.model, max_steps=args.max_steps)
    print_report(result, args.model)

    if args.log:
        await log_to_mlflow(result, args.model)

    return 0 if result.success_rate >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
