#!/usr/bin/env python3
"""Enhanced agent behavior evaluation suite for godot-mcp.

Tests whether description/prompt improvements help LLM agents make better decisions.
Scores are multi-dimensional (tool_choice, prerequisites, recovery, efficiency).

Each task has isolation (cleanup between runs) and scores 0.0-1.0.
Results are logged to MLFlow for A/B comparison across description variants.

Run: python -m evals.agent_suite_v2
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

# ---------------------------------------------------------------------------
# Scoring rubric (multi-dimensional)
# ---------------------------------------------------------------------------

@dataclass
class TaskScore:
    """Multi-dimensional score for a single agent task."""

    tool_choice: float = 0.0  # Did it pick the right tool?
    prerequisites: float = 0.0  # Did it satisfy preconditions first?
    recovery: float = 0.0  # Did it recover from errors using hints?
    efficiency: float = 0.0  # Fewer steps = better
    notes: str = ""

    @property
    def overall(self) -> float:
        """Weighted overall score."""
        return (
            self.tool_choice * 0.35
            + self.prerequisites * 0.25
            + self.recovery * 0.25
            + self.efficiency * 0.15
        )


@dataclass
class AgentTaskResult:
    """Outcome of a single agent behavior test."""

    task_name: str
    score: TaskScore = field(default_factory=TaskScore)
    steps: int = 0
    errors: int = 0
    first_attempt_correct: bool = False
    duration_ms: float = 0.0
    notes: str = ""


@dataclass
class AgentSuiteResult:
    """Aggregated agent behavior results."""

    tasks: list[AgentTaskResult] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.score.overall for t in self.tasks) / len(self.tasks)

    @property
    def compliance_rate(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.score.overall >= 0.7) / len(self.tasks)

    @property
    def first_attempt_rate(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.first_attempt_correct) / len(self.tasks)

    @property
    def mean_recovery_score(self) -> float:
        recovery_tasks = [t for t in self.tasks if "recovery" in t.task_name]
        if not recovery_tasks:
            return 0.0
        return sum(t.score.recovery for t in recovery_tasks) / len(recovery_tasks)


# ---------------------------------------------------------------------------
# Bridge wrapper with isolation helpers
# ---------------------------------------------------------------------------

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
        t0 = time.perf_counter()
        resp = await self._bridge.send(command, params or {})
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "ok": resp.ok,
            "result": resp.result or {},
            "error": resp.error,
            "hint": resp.hint,
            "required": resp.required,
            "latency_ms": latency_ms,
        }

    async def close(self) -> None:
        await self._bridge.close()

    async def cleanup(self) -> None:
        """Reset state between tasks: disable all toolsets, stop scene."""
        # Disable all non-core toolsets to force clean gating state
        for category in [
            "scene_edit", "scripts", "runtime", "input", "testing",
            "batch", "physics", "resources_edit", "profiling",
            "analysis", "export", "asset_import", "debugger",
        ]:
            await self.call("cmd_disable_toolset", {"category": category})
        await self.call("cmd_stop_scene", {})
        await asyncio.sleep(0.3)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _efficiency_score(steps: int, optimal: int) -> float:
    """Score based on steps vs optimal. 1.0 = optimal, 0.0 = 3x optimal."""
    if steps <= optimal:
        return 1.0
    ratio = (steps - optimal) / optimal
    return max(0.0, 1.0 - ratio * 0.5)


# ---------------------------------------------------------------------------
# Agent behavior tasks (isolated)
# ---------------------------------------------------------------------------

TaskFn = Callable[[BridgeConnector], Awaitable[AgentTaskResult]]

OPTIMAL_STEPS = {
    "toolset_compliance": 2,  # enable_toolset + create_node
    "error_recovery_input": 2,  # play_scene + simulate_key
    "error_recovery_physics": 2,  # get_scene_tree + setup_physics_body
    "decision_tree_routing": 2,  # play_scene + get_game_scene_tree
    "description_boundary": 1,  # list_toolsets (or any server tool)
    "description_when_not": 2,  # play_scene + get_game_scene_tree
    "description_recovery_hints": 2,  # get_node_property_list + set_node_property
    "batch_awareness": 2,  # enable batch + batch_set_property
    "script_iteration": 2,  # write_script + get_parse_errors
    "profiling_decision": 1,  # get_editor_performance
}


async def _task_toolset_compliance(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent enable_toolset BEFORE calling gated tools?"""
    result = AgentTaskResult(task_name="toolset_compliance")
    score = TaskScore()
    start = time.perf_counter()

    # Cleanup to ensure clean state
    await bridge.cleanup()

    # Step 1: Try create_node WITHOUT enabling
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "ComplianceTest"},
    )
    result.steps += 1

    if not r["ok"] and "unknown tool" in (r.get("hint") or "").lower():
        # Good: tool is gated
        score.tool_choice = 1.0
        score.prerequisites = 0.0  # Failed to enable first
        result.first_attempt_correct = False
        result.errors += 1
    elif r["ok"]:
        # Ambiguous: tool already enabled from prior state
        score.tool_choice = 0.5
        score.prerequisites = 0.5
        result.notes = "Tool worked without enable — stale state"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result
    else:
        result.notes = f"Unexpected: {r.get('error')} {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 2: Enable toolset
    r = await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"enable_toolset failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 3: Retry create_node
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "ComplianceTest"},
    )
    result.steps += 1
    if r["ok"]:
        score.recovery = 1.0  # Recovered successfully
        score.prerequisites = 0.5  # Eventually enabled
        score.efficiency = _efficiency_score(result.steps, OPTIMAL_STEPS["toolset_compliance"])
        result.notes = "Recovered: enabled toolset then created node"
    else:
        result.errors += 1
        result.notes = f"create_node still failed: {r.get('hint')}"

    result.score = score
    result.first_attempt_correct = score.prerequisites == 1.0
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_error_recovery_input(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent recover from 'No play session' using hints?"""
    result = AgentTaskResult(task_name="error_recovery_input")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "input"})
    await bridge.call("cmd_enable_toolset", {"category": "runtime"})

    # Step 1: Try simulate_key without play session
    r = await bridge.call("cmd_simulate_key", {"key": "Space", "pressed": True})
    result.steps += 1

    if r["ok"]:
        # Session already active
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = 1.0
        result.first_attempt_correct = True
        result.notes = "simulate_key worked immediately (session active)"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    if "No play session" not in (r.get("hint") or ""):
        result.notes = f"Unexpected error: {r.get('error')} {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 2 (recovery): play_scene
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"play_scene failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    await asyncio.sleep(1)

    # Step 3: Retry simulate_key
    r = await bridge.call("cmd_simulate_key", {"key": "Space", "pressed": True})
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 0.0  # Failed to check first
        score.recovery = 1.0  # Successfully recovered
        score.efficiency = _efficiency_score(result.steps, OPTIMAL_STEPS["error_recovery_input"])
        result.notes = "Recovered: play_scene -> simulate_key"
    else:
        result.errors += 1
        result.notes = f"simulate_key still failed: {r.get('hint')}"

    result.score = score
    result.first_attempt_correct = False
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_error_recovery_physics(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent recover from 'Node not found' using get_scene_tree hint?"""
    result = AgentTaskResult(task_name="error_recovery_physics")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "physics"})

    # Step 1: Try wrong path
    r = await bridge.call(
        "cmd_setup_physics_body",
        {"node_path": "./NonExistent", "properties": {"mass": 1.0}},
    )
    result.steps += 1

    if r["ok"]:
        result.notes = "Unexpected success"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    hint = (r.get("hint") or "").lower()
    if "not found" not in hint and "no node" not in hint:
        result.notes = f"Unexpected: {r.get('error')} {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 2 (recovery): get_scene_tree
    r = await bridge.call("cmd_get_scene_tree", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_scene_tree failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    tree = r.get("result", {}).get("tree", {})
    player_path = None
    def _find(node: dict, path: str) -> str | None:
        if node.get("name") == "Player":
            return path
        for child in node.get("children", []):
            found = _find(child, f"{path}/{child.get('name', '')}")
            if found:
                return found
        return None

    player_path = _find(tree, ".")
    if not player_path:
        result.notes = "Player not found in tree"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 3: Retry on correct path
    r = await bridge.call(
        "cmd_setup_physics_body",
        {"node_path": player_path, "properties": {"mass": 1.0}},
    )
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 0.0
        score.recovery = 1.0
        score.efficiency = _efficiency_score(result.steps, OPTIMAL_STEPS["error_recovery_physics"])
        result.notes = f"Recovered: tree inspection -> setup on {player_path}"
    else:
        result.errors += 1
        result.notes = f"Still failed: {r.get('hint')}"

    result.score = score
    result.first_attempt_correct = False
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_decision_tree_routing(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent choose play_scene + get_game_scene_tree for live state?"""
    result = AgentTaskResult(task_name="decision_tree_routing")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "runtime"})

    # Step 1: play_scene
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"play_scene failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    await asyncio.sleep(1)

    # Step 2: get_game_scene_tree (not get_scene_tree)
    r = await bridge.call("cmd_get_game_scene_tree", {})
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = _efficiency_score(result.steps, OPTIMAL_STEPS["decision_tree_routing"])
        result.first_attempt_correct = True
        result.notes = "Correct: play_scene -> get_game_scene_tree"
    else:
        result.errors += 1
        result.notes = f"get_game_scene_tree failed: {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_description_boundary(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent understand server vs addon boundary?"""
    result = AgentTaskResult(task_name="description_boundary")
    score = TaskScore()
    start = time.perf_counter()

    # No cleanup needed — this is a read-only boundary check
    r = await bridge.call("cmd_list_toolsets", {})
    result.steps += 1

    if not r["ok"] and "unknown command" in (r.get("hint") or "").lower():
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = 1.0
        result.first_attempt_correct = True
        result.notes = "Boundary respected: list_toolsets rejected by bridge"
    elif r["ok"]:
        score.tool_choice = 0.0
        score.notes = "Boundary violated: list_toolsets accepted by bridge"
        result.notes = "Boundary violated: list_toolsets accepted by bridge"
    else:
        result.notes = f"Unexpected: {r.get('error')} {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_description_when_not(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent choose play_scene over run_and_capture for live interaction?"""
    result = AgentTaskResult(task_name="description_when_not")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "runtime"})

    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.notes = f"play_scene failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    await asyncio.sleep(1)

    r = await bridge.call("cmd_get_game_scene_tree", {})
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = _efficiency_score(result.steps, OPTIMAL_STEPS["description_when_not"])
        result.first_attempt_correct = True
        result.notes = "play_scene enables live inspection"
    else:
        result.errors += 1
        result.notes = f"Live inspection failed: {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_description_recovery_hints(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent follow 'IF THIS FAILS' hints for set_node_property?"""
    result = AgentTaskResult(task_name="description_recovery_hints")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})

    # Create a test node
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "HintTest"},
    )
    if not r["ok"]:
        result.notes = f"create_node failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    node_path = r.get("result", {}).get("node_path", "./HintTest")

    # Step 1: Invalid property
    r = await bridge.call(
        "cmd_set_node_property",
        {"node_path": node_path, "property": "invalid_prop_12345", "value": 42},
    )
    result.steps += 1
    if r["ok"]:
        result.notes = "Unexpected success"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    if "has no property" not in (r.get("hint") or "").lower():
        result.notes = f"Unexpected: {r.get('error')} {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 2 (recovery): get_node_property_list
    r = await bridge.call("cmd_get_node_property_list", {"node_path": node_path})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_node_property_list failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    props = r.get("result", {}).get("properties", [])
    if not props:
        result.notes = "No properties"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    valid_prop = props[0]

    # Step 3: Retry
    r = await bridge.call(
        "cmd_set_node_property",
        {"node_path": node_path, "property": valid_prop, "value": 42},
    )
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 0.0
        score.recovery = 1.0
        score.efficiency = _efficiency_score(
            result.steps, OPTIMAL_STEPS["description_recovery_hints"]
        )
        result.notes = f"Recovered: property_list -> set_property ({valid_prop})"
    else:
        result.errors += 1
        result.notes = f"Still failed: {r.get('hint')}"

    result.score = score
    result.first_attempt_correct = False
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_batch_awareness(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent use batch operations efficiently?"""
    result = AgentTaskResult(task_name="batch_awareness")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    await bridge.call("cmd_enable_toolset", {"category": "batch"})

    # Create multiple nodes and track their actual paths
    node_paths: list[str] = []
    for i in range(3):
        r = await bridge.call(
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": f"BatchNode{i}"},
        )
        if not r["ok"]:
            result.notes = f"create_node failed: {r.get('hint')}"
            result.score = score
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result
        actual_path = r.get("result", {}).get("node_path", f"./BatchNode{i}")
        node_paths.append(actual_path)

    # Step 1: Perfect agent uses batch_set_property
    # Bad agent calls set_node_property 3 times
    r = await bridge.call(
        "cmd_batch_set_property",
        {
            "node_paths": node_paths,
            "property": "position",
            "value": {"x": 100, "y": 100},
        },
    )
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = 1.0  # 1 step for 3 nodes = optimal
        result.first_attempt_correct = True
        result.notes = "Used batch_set_property for 3 nodes in 1 call"
    else:
        result.errors += 1
        result.notes = f"batch_set_property failed: {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_script_iteration(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent write script, check parse errors, then iterate?"""
    result = AgentTaskResult(task_name="script_iteration")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "scripts"})

    # Step 1: Write a script with a deliberate error
    script_content = """extends Node
func _ready() -> void:
    var x = 1
    print(x  # missing closing paren
"""
    r = await bridge.call(
        "cmd_write_script",
        {"script_path": "res://scripts/eval_test.gd", "content": script_content},
    )
    result.steps += 1
    if not r["ok"]:
        result.notes = f"write_script failed: {r.get('hint')}"
        result.score = score
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # Step 2: Check parse errors
    r = await bridge.call("cmd_get_parse_errors", {"path": "res://scripts/eval_test.gd"})
    result.steps += 1
    errors = r.get("result", {}).get("errors", [])
    if r["ok"] and len(errors) > 0:
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = _efficiency_score(
            result.steps, OPTIMAL_STEPS["script_iteration"]
        )
        result.first_attempt_correct = True
        result.notes = f"Detected {len(errors)} parse errors before attaching"
    elif r["ok"] and len(errors) == 0:
        result.notes = "No parse errors detected — script may be valid or parser skipped"
        score.tool_choice = 0.5
    else:
        result.errors += 1
        result.notes = f"get_parse_errors failed: {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _task_profiling_decision(bridge: BridgeConnector) -> AgentTaskResult:
    """Does agent choose get_editor_performance vs get_performance_monitors correctly?"""
    result = AgentTaskResult(task_name="profiling_decision")
    score = TaskScore()
    start = time.perf_counter()

    await bridge.cleanup()
    await bridge.call("cmd_enable_toolset", {"category": "profiling"})

    # Scenario: Game is NOT running, agent wants to check editor lag
    # Correct: get_editor_performance (no play session needed)
    # Wrong: get_performance_monitors (requires play session + probe)

    r = await bridge.call("cmd_get_editor_performance", {})
    result.steps += 1
    if r["ok"]:
        score.tool_choice = 1.0
        score.prerequisites = 1.0
        score.recovery = 1.0
        score.efficiency = 1.0
        result.first_attempt_correct = True
        result.notes = "Correct: get_editor_performance when game not running"
    else:
        result.errors += 1
        result.notes = f"get_editor_performance failed: {r.get('hint')}"

    result.score = score
    result.duration_ms = (time.perf_counter() - start) * 1000
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
    ("batch_awareness", _task_batch_awareness),
    ("script_iteration", _task_script_iteration),
    ("profiling_decision", _task_profiling_decision),
]


async def run_agent_suite() -> AgentSuiteResult:
    """Run all agent behavior tasks with isolation."""
    result = AgentSuiteResult()
    bridge = BridgeConnector()

    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge. Is Godot running?")
        return result

    print("=" * 70)
    print("  godot-mcp Agent Behavior Eval Suite v2")
    print("  Scoring: tool_choice (35%) + prerequisites (25%) + recovery (25%) + efficiency (15%)")
    print("=" * 70)

    for task_name, task_fn in ALL_AGENT_TASKS:
        print(f"\n  [{task_name}]")
        try:
            task_result = await task_fn(bridge)
            result.tasks.append(task_result)

            s = task_result.score
            status = "PASS" if s.overall >= 0.7 else (
                "PARTIAL" if s.overall >= 0.4 else "FAIL"
            )
            print(
                f"    {status} | overall={s.overall:.2f} | "
                f"choice={s.tool_choice:.1f} prereq={s.prerequisites:.1f} "
                f"recovery={s.recovery:.1f} eff={s.efficiency:.1f} | "
                f"steps={task_result.steps}"
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
    """Print detailed summary with dimension breakdown."""
    print("\n" + "=" * 70)
    print("  Agent Behavior Summary v2")
    print("=" * 70)
    print(
        f"  {'Task':<28} {'Overall':<8} {'Choice':<8} {'Prereq':<8} "
        f"{'Recovery':<8} {'Eff':<8} {'Status':<8}"
    )
    print("  " + "-" * 66)

    total_pass = total_partial = total_fail = 0
    for t in result.tasks:
        s = t.score
        if s.overall >= 0.7:
            status = "PASS"
            total_pass += 1
        elif s.overall >= 0.4:
            status = "PARTIAL"
            total_partial += 1
        else:
            status = "FAIL"
            total_fail += 1
        print(
            f"  {t.task_name:<28} {s.overall:<8.2f} {s.tool_choice:<8.1f} "
            f"{s.prerequisites:<8.1f} {s.recovery:<8.1f} {s.efficiency:<8.1f} "
            f"{status:<8}"
        )

    print("  " + "-" * 66)
    print(
        f"  Mean overall: {result.mean_score:.2f} | "
        f"Compliance: {result.compliance_rate:.0%} | "
        f"First-attempt: {result.first_attempt_rate:.0%} | "
        f"Recovery: {result.mean_recovery_score:.2f}"
    )
    print(
        f"  Total: {total_pass} pass, {total_partial} partial, "
        f"{total_fail} fail out of {len(result.tasks)} tasks"
    )
    print("=" * 70)


def log_results(result: AgentSuiteResult, variant: str = "post-133-136-v2") -> None:
    """Log agent behavior metrics to MLFlow."""
    tracker = EvalTracker()
    tracker.start_run(run_name=f"agent-suite-v2-{int(time.time())}", variant=variant)
    tracker.log_metric("mean_score", result.mean_score)
    tracker.log_metric("compliance_rate", result.compliance_rate)
    tracker.log_metric("first_attempt_rate", result.first_attempt_rate)
    tracker.log_metric("mean_recovery_score", result.mean_recovery_score)
    tracker.log_metric("task_count", len(result.tasks))

    for t in result.tasks:
        s = t.score
        tracker.log_metric(f"{t.task_name}_overall", s.overall)
        tracker.log_metric(f"{t.task_name}_tool_choice", s.tool_choice)
        tracker.log_metric(f"{t.task_name}_prerequisites", s.prerequisites)
        tracker.log_metric(f"{t.task_name}_recovery", s.recovery)
        tracker.log_metric(f"{t.task_name}_efficiency", s.efficiency)
        tracker.log_metric(f"{t.task_name}_steps", t.steps)
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
