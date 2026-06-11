#!/usr/bin/env python3
"""Agent behavior evaluation suite for godot-mcp.

Tests whether an LLM agent (simulated by structured test logic) correctly:
1. Follows the toolset gating protocol (enable before use)
2. Recovers from precondition/validation errors using embedded hints
3. Chooses the right tool based on intent (decision tree / WHEN/WHEN-NOT)
4. Distinguishes server-side vs addon tools (boundary awareness)

Each task returns a score 0.0–1.0 and metrics (steps, errors, first_attempt_correct).
Scores are logged to MLFlow alongside infrastructure evals for A/B comparison.

Run: python -m evals.agent_suite
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

sys.path.insert(0, "/Users/johnd/Development/godot-mcp")

from evals.mlflow_tracker import EvalTracker
from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig


@dataclass
class AgentTaskResult:
    """Outcome of a single agent behavior test."""

    task_name: str
    score: float = 0.0  # 0.0–1.0
    steps: int = 0
    errors: int = 0
    first_attempt_correct: bool = False
    notes: str = ""


@dataclass
class AgentSuiteResult:
    """Aggregated agent behavior results."""

    tasks: list[AgentTaskResult] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.score for t in self.tasks) / len(self.tasks)

    @property
    def compliance_rate(self) -> float:
        """% of tasks that achieved score >= 0.8 (good agent behavior)."""
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.score >= 0.8) / len(self.tasks)

    @property
    def recovery_rate(self) -> float:
        """% of error-recovery tasks that scored >= 0.5."""
        recovery_tasks = [t for t in self.tasks if "recovery" in t.task_name]
        if not recovery_tasks:
            return 0.0
        return sum(1 for t in recovery_tasks if t.score >= 0.5) / len(recovery_tasks)

    @property
    def first_attempt_rate(self) -> float:
        """% of tasks where the first tool choice was correct."""
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.first_attempt_correct) / len(self.tasks)


class BridgeConnector:
    def __init__(self) -> None:
        self._bridge = Bridge(BridgeConfig.from_env())

    async def connect(self) -> bool:
        try:
            await self._bridge.connect()
            return self._bridge.connected
        except Exception:
            return False

    async def call(self, command: str, params: dict | None = None) -> dict:
        resp = await self._bridge.send(command, params or {})
        return {
            "ok": resp.ok,
            "result": resp.result or {},
            "error": resp.error,
            "hint": resp.hint,
            "required": resp.required,
        }

    async def close(self) -> None:
        await self._bridge.close()


# ---------------------------------------------------------------------------
# Agent behavior tasks
# ---------------------------------------------------------------------------

TaskFn = Callable[[BridgeConnector], Awaitable[AgentTaskResult]]


async def _task_toolset_compliance(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent enable_toolset BEFORE calling a gated tool?

    Perfect agent: calls enable_toolset('scene_edit') first, then create_node.
    Bad agent: calls create_node directly (fails with 'unknown tool').
    """
    result = AgentTaskResult(task_name="toolset_compliance")

    # Step 1 (attempt): Try create_node WITHOUT enabling
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "ComplianceTest"},
    )
    result.steps += 1

    if r["ok"]:
        # Tool was already enabled from a prior test — reset by restarting Godot
        # or the addon doesn't gate properly. Mark as ambiguous.
        result.score = 0.5
        result.notes = "Tool worked without enable — may be stale state"
        return result

    if r["error"] == "TOOL_ERROR" and "unknown tool" in (r.get("hint") or "").lower():
        # Expected failure — the agent should have enabled first
        result.first_attempt_correct = False
        result.errors += 1
    else:
        result.notes = f"Unexpected error: {r.get('error')} {r.get('hint')}"
        return result

    # Step 2 (recovery): Enable the toolset
    r = await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"enable_toolset failed: {r.get('hint')}"
        return result

    # Step 3: Retry create_node
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "ComplianceTest"},
    )
    result.steps += 1
    if r["ok"]:
        # Recovered successfully — partial score (needed 2 steps instead of 1)
        result.score = 0.5
        result.notes = "Recovered after enable_toolset but first attempt was wrong"
    else:
        result.errors += 1
        result.notes = f"create_node still failed after enable: {r.get('hint')}"

    result.first_attempt_correct = result.score == 1.0
    return result


async def _task_error_recovery_input(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent recover from 'No play session' by calling play_scene first?

    Simulates an agent that reads the IF THIS FAILS hint in simulate_key's docstring.
    Perfect agent: calls play_scene() before simulate_key().
    Recovering agent: simulate_key fails, then play_scene, then retry simulate_key.
    Bad agent: simulate_key fails and agent stalls.
    """
    result = AgentTaskResult(task_name="error_recovery_input")

    # Ensure no play session is active
    await bridge.call("cmd_stop_scene", {})
    await asyncio.sleep(0.5)

    # Step 1: Try simulate_key without play session
    r = await bridge.call("cmd_simulate_key", {"key": "Space", "pressed": True})
    result.steps += 1

    if r["ok"]:
        # Unexpected — maybe a session was already running
        result.score = 1.0
        result.first_attempt_correct = True
        result.notes = "simulate_key worked without explicit play_scene (session active)"
        return result

    if "No play session" not in (r.get("hint") or ""):
        result.notes = f"Unexpected error: {r.get('error')} {r.get('hint')}"
        return result

    # Step 2 (recovery): Call play_scene
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"play_scene failed: {r.get('hint')}"
        return result

    await asyncio.sleep(1)

    # Step 3: Retry simulate_key
    r = await bridge.call("cmd_simulate_key", {"key": "Space", "pressed": True})
    result.steps += 1
    if r["ok"]:
        result.score = 0.5  # Recovered but needed extra steps
        result.notes = "Recovered: play_scene -> simulate_key (2 extra steps)"
    else:
        result.errors += 1
        result.notes = f"simulate_key still failed after play_scene: {r.get('hint')}"

    result.first_attempt_correct = False
    return result


async def _task_error_recovery_physics(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent recover from 'Node not found' by checking get_scene_tree first?

    Simulates reading the IF THIS FAILS hint in setup_physics_body.
    Perfect agent: get_scene_tree -> find correct node path -> setup_physics_body.
    """
    result = AgentTaskResult(task_name="error_recovery_physics")

    # Ensure physics toolset is enabled
    await bridge.call("cmd_enable_toolset", {"category": "physics"})

    # Step 1: Try setup_physics_body on a likely-wrong path
    r = await bridge.call(
        "cmd_setup_physics_body",
        {"node_path": "./NonExistent", "properties": {"mass": 1.0}},
    )
    result.steps += 1

    if r["ok"]:
        result.notes = "Unexpected success — node may exist"
        return result

    hint = (r.get("hint") or "").lower()
    if "not found" not in hint and "no node" not in hint:
        result.notes = f"Unexpected error: {r.get('error')} {r.get('hint')}"
        return result

    # Step 2 (recovery): Inspect scene tree to find a valid physics body
    # First ensure inspection toolset is available
    r = await bridge.call("cmd_get_scene_tree", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_scene_tree failed: {r.get('hint')}"
        return result

    tree = r.get("result", {}).get("tree", {})
    # Try to find Player node which we know exists in the vampire scene
    player_path = None
    def _find_player(node: dict, path: str) -> str | None:
        if node.get("name") == "Player":
            return path
        for child in node.get("children", []):
            found = _find_player(child, f"{path}/{child.get('name', '')}")
            if found:
                return found
        return None

    player_path = _find_player(tree, ".")

    if not player_path:
        result.notes = "Player node not found in scene tree"
        return result

    # Step 3: Retry setup_physics_body on the actual Player node
    r = await bridge.call(
        "cmd_setup_physics_body",
        {"node_path": player_path, "properties": {"mass": 1.0}},
    )
    result.steps += 1
    if r["ok"]:
        result.score = 0.5
        result.notes = f"Recovered: get_scene_tree -> setup_physics_body on {player_path}"
    else:
        result.errors += 1
        result.notes = f"setup_physics_body still failed: {r.get('hint')}"

    result.first_attempt_correct = False
    return result


async def _task_decision_tree_routing(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent choose the right tool based on intent?

    Intent: "Run the game and inspect live state"
    Correct: enable_toolset('runtime') -> play_scene() -> get_game_scene_tree()
    Wrong: get_scene_tree() (reads static editor tree, not live game)
    """
    result = AgentTaskResult(task_name="decision_tree_routing")

    # Ensure no play session
    await bridge.call("cmd_stop_scene", {})
    await asyncio.sleep(0.5)

    # Enable required toolsets
    await bridge.call("cmd_enable_toolset", {"category": "runtime"})

    # Step 1: Agent should call play_scene for live interaction
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"play_scene failed: {r.get('hint')}"
        return result

    await asyncio.sleep(1)

    # Step 2: Agent should call get_game_scene_tree (not get_scene_tree)
    r = await bridge.call("cmd_get_game_scene_tree", {})
    result.steps += 1
    if r["ok"]:
        result.score = 1.0
        result.first_attempt_correct = True
        result.notes = "Correct routing: play_scene -> get_game_scene_tree"
    else:
        result.errors += 1
        result.notes = f"get_game_scene_tree failed: {r.get('hint')}"

    return result


async def _task_description_boundary(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent understand server vs addon boundary?

    Correct: list_toolsets and enable_toolset are called server-side (work)
    Wrong: Calling them through the addon bridge fails with 'unknown tool'
    This task verifies the boundary is respected.
    """
    result = AgentTaskResult(task_name="description_boundary")

    # Step 1: Call list_toolsets through the bridge (server tool via bridge)
    r = await bridge.call("cmd_list_toolsets", {})
    result.steps += 1

    # In our architecture, list_toolsets IS handled server-side.
    # If the bridge returns "unknown command", the boundary is respected.
    if not r["ok"] and "unknown command" in (r.get("hint") or "").lower():
        result.score = 1.0
        result.first_attempt_correct = True
        result.notes = "Boundary respected: list_toolsets rejected by bridge"
    elif r["ok"]:
        result.score = 0.0
        result.notes = "Boundary violation: list_toolsets accepted by bridge"
    else:
        result.notes = f"Unexpected: {r.get('error')} {r.get('hint')}"

    return result


async def _task_description_when_not(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent choose play_scene over run_and_capture for live interaction?

    Intent: "I want to simulate input and inspect the running game"
    Correct: play_scene (live editor session with probe)
    Wrong: run_and_capture (headless, no live interaction)
    """
    result = AgentTaskResult(task_name="description_when_not")

    # We can't truly measure agent intent, but we can verify play_scene works
    # for the live-interaction use case while run_and_capture does not support it.

    # Step 1: Call play_scene (correct for live interaction)
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"play_scene failed: {r.get('hint')}"
        return result

    await asyncio.sleep(1)

    # Step 2: Verify live tools work (get_game_scene_tree)
    r = await bridge.call("cmd_get_game_scene_tree", {})
    result.steps += 1
    if r["ok"]:
        result.score = 1.0
        result.first_attempt_correct = True
        result.notes = "play_scene enables live inspection (correct choice)"
    else:
        result.errors += 1
        result.notes = f"Live inspection failed: {r.get('hint')}"

    return result


async def _task_description_recovery_hints(bridge: BridgeConnector) -> AgentTaskResult:
    """Does the agent follow embedded IF THIS FAILS hints?

    Scenario: set_node_property on wrong property name
    Hint in docstring: "IF THIS FAILS with 'has no property' -> use get_node_property_list()"
    Perfect agent: get_node_property_list -> set_node_property with valid property.
    """
    result = AgentTaskResult(task_name="description_recovery_hints")

    # Ensure scene_edit is enabled and a node exists
    await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    
    # Create node under scene root using relative path
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "HintTest"},
    )
    if not r["ok"]:
        result.notes = f"create_node failed: {r.get('hint')}"
        return result

    # Step 1: Try set_node_property with invalid property
    # Use the path reported by create_node if available, otherwise fallback
    node_path = r.get("result", {}).get("node_path", "./HintTest")
    r = await bridge.call(
        "cmd_set_node_property",
        {"node_path": node_path, "property": "invalid_property_12345", "value": 42},
    )
    result.steps += 1

    if r["ok"]:
        result.notes = "Unexpected success — property was accepted"
        return result

    if "has no property" not in (r.get("hint") or "").lower():
        result.notes = f"Unexpected error: {r.get('error')} {r.get('hint')}"
        return result

    # Step 2 (recovery): Call get_node_property_list
    r = await bridge.call("cmd_get_node_property_list", {"node_path": node_path})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_node_property_list failed: {r.get('hint')}"
        return result

    props = r.get("result", {}).get("properties", [])
    if not props:
        result.notes = "No properties returned"
        return result

    valid_prop = props[0]

    # Step 3: Retry with valid property
    r = await bridge.call(
        "cmd_set_node_property",
        {"node_path": node_path, "property": valid_prop, "value": 42},
    )
    result.steps += 1
    if r["ok"]:
        result.score = 0.5
        result.notes = f"Recovered: get_node_property_list -> set_node_property ({valid_prop})"
    else:
        result.errors += 1
        result.notes = f"set_node_property still failed: {r.get('hint')}"

    result.first_attempt_correct = False
    return result


# ---------------------------------------------------------------------------
# Suite orchestration
# ---------------------------------------------------------------------------

ALL_AGENT_TASKS: list[tuple[str, TaskFn]] = [
    ("toolset_compliance", _task_toolset_compliance),
    ("error_recovery_input", _task_error_recovery_input),
    ("error_recovery_physics", _task_error_recovery_physics),
    ("decision_tree_routing", _task_decision_tree_routing),
    ("description_boundary", _task_description_boundary),
    ("description_when_not", _task_description_when_not),
    ("description_recovery_hints", _task_description_recovery_hints),
]


async def run_agent_suite() -> AgentSuiteResult:
    """Run all agent behavior tasks and return aggregated results."""
    result = AgentSuiteResult()
    bridge = BridgeConnector()

    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge. Is Godot running?")
        return result

    print("=" * 70)
    print("  godot-mcp Agent Behavior Eval Suite")
    print("=" * 70)

    for task_name, task_fn in ALL_AGENT_TASKS:
        print(f"\n  [{task_name}]")
        try:
            task_result = await task_fn(bridge)
            result.tasks.append(task_result)
            status = "PASS" if task_result.score >= 0.8 else (
                "PARTIAL" if task_result.score >= 0.5 else "FAIL"
            )
            print(
                f"    {status} | score={task_result.score:.1f} | "
                f"steps={task_result.steps} | errors={task_result.errors} | "
                f"first_ok={task_result.first_attempt_correct}"
            )
            if task_result.notes:
                print(f"    Notes: {task_result.notes}")
        except Exception as e:
            print(f"    💥 EXCEPTION: {type(e).__name__}: {e}")
            result.tasks.append(
                AgentTaskResult(task_name=task_name, notes=str(e))
            )

    await bridge.close()
    return result


def print_summary(result: AgentSuiteResult) -> None:
    """Print a comparison table of all agent tasks."""
    print("\n" + "=" * 70)
    print("  Agent Behavior Summary")
    print("=" * 70)
    print(
        f"  {'Task':<30} {'Score':<8} {'Steps':<8} {'Errors':<8} "
        f"{'First OK':<10} {'Status':<8}"
    )
    print("  " + "-" * 66)

    total_pass = total_partial = total_fail = 0
    for t in result.tasks:
        if t.score >= 0.8:
            status = "PASS"
            total_pass += 1
        elif t.score >= 0.5:
            status = "PARTIAL"
            total_partial += 1
        else:
            status = "FAIL"
            total_fail += 1
        print(
            f"  {t.task_name:<30} {t.score:<8.1f} {t.steps:<8} "
            f"{t.errors:<8} {str(t.first_attempt_correct):<10} {status:<8}"
        )

    print("  " + "-" * 66)
    print(
        f"  Mean score: {result.mean_score:.2f} | "
        f"Compliance: {result.compliance_rate:.0%} | "
        f"Recovery: {result.recovery_rate:.0%} | "
        f"First-attempt: {result.first_attempt_rate:.0%}"
    )
    print(
        f"  Total: {total_pass} pass, {total_partial} partial, "
        f"{total_fail} fail out of {len(result.tasks)} tasks"
    )
    print("=" * 70)


def log_results(result: AgentSuiteResult) -> None:
    """Log agent behavior metrics to MLFlow."""
    tracker = EvalTracker()
    tracker.start_run(
        run_name=f"agent-suite-{int(time.time())}",
        variant="post-133-136",
    )
    tracker.log_metric("mean_score", result.mean_score)
    tracker.log_metric("compliance_rate", result.compliance_rate)
    tracker.log_metric("recovery_rate", result.recovery_rate)
    tracker.log_metric("first_attempt_rate", result.first_attempt_rate)
    tracker.log_metric("task_count", len(result.tasks))

    for t in result.tasks:
        tracker.log_metric(f"{t.task_name}_score", t.score)
        tracker.log_metric(f"{t.task_name}_steps", t.steps)
        tracker.log_metric(f"{t.task_name}_errors", t.errors)
        if t.notes:
            tracker.log_param(f"{t.task_name}_notes", t.notes[:250])

    tracker.end_run()
    print("\n📊 Logged to MLFlow: https://mlflow.johndstudios.net/#/experiments/55")


async def main() -> None:
    results = await run_agent_suite()
    print_summary(results)
    if results.tasks:
        log_results(results)


if __name__ == "__main__":
    asyncio.run(main())
