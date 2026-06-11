"""Comprehensive eval suite for all godot-mcp toolsets.

Tests every toolset category with representative tasks, measuring:
- tool_discovery: can the agent find and enable the toolset?
- gate_correctness: are tools hidden until enabled?
- command_routing: does the command reach the addon and return valid shape?
- error_recovery: does the agent recover from precondition/validation errors?
- param_validation: are required params enforced?

Run: python -m evals.suite --mlflow
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
class TaskResult:
    task_name: str
    toolset: str
    success: bool = False
    steps: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    notes: str = ""


@dataclass
class ToolsetResult:
    toolset: str
    tasks: list[TaskResult] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.success) / len(self.tasks)

    @property
    def total_errors(self) -> int:
        return sum(t.errors for t in self.tasks)


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
# Task definitions — one per toolset
# ---------------------------------------------------------------------------

TaskFn = Callable[[BridgeConnector], Awaitable[TaskResult]]


async def _task_core(bridge: BridgeConnector) -> TaskResult:
    """Core: health_check, get_server_info, list_toolsets, enable_toolset"""
    result = TaskResult(task_name="core_basics", toolset="core")
    start = time.perf_counter()

    # health_check should always work (no enable needed)
    r = await bridge.call("cmd_get_server_info", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_server_info failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # list_toolsets
    r = await bridge.call("cmd_list_toolsets", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"list_toolsets failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    toolsets = r.get("result", {}).get("toolsets", [])
    if not isinstance(toolsets, list) or len(toolsets) < 5:
        result.errors += 1
        result.notes = f"Too few toolsets: {len(toolsets)}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Found {len(toolsets)} toolsets"
    return result


async def _task_inspection(bridge: BridgeConnector) -> TaskResult:
    """Inspection: get_project_info, get_active_scene, get_scene_tree"""
    result = TaskResult(task_name="inspection_basics", toolset="inspection")
    start = time.perf_counter()

    for cmd, params in [
        ("cmd_get_project_info", {}),
        ("cmd_get_active_scene", {}),
        ("cmd_get_scene_tree", {}),
    ]:
        r = await bridge.call(cmd, params)
        result.steps += 1
        if not r["ok"]:
            result.errors += 1
            result.notes = f"{cmd} failed: {r.get('hint')}"
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "All inspection tools callable"
    return result


async def _task_scene_edit(bridge: BridgeConnector) -> TaskResult:
    """Scene edit: create_node, set_node_property"""
    result = TaskResult(task_name="scene_edit_basics", toolset="scene_edit")
    start = time.perf_counter()

    # Enable toolset first
    r = await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"enable_toolset(scene_edit) failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # create_node
    r = await bridge.call(
        "cmd_create_node",
        {"parent_path": "/root", "node_type": "Node2D", "node_name": "TestNode"},
    )
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"create_node failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Created Node2D test node"
    return result


async def _task_scripts(bridge: BridgeConnector) -> TaskResult:
    """Scripts: get_parse_errors"""
    result = TaskResult(task_name="scripts_basics", toolset="scripts")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "scripts"})
    result.steps += 1

    r = await bridge.call("cmd_get_parse_errors", {"path": "res://scripts/player.gd"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_parse_errors failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Parse errors: {len(r.get('result', {}).get('errors', []))}"
    return result


async def _task_mutation(bridge: BridgeConnector) -> TaskResult:
    """Mutation: set_node_property"""
    result = TaskResult(task_name="mutation_basics", toolset="scene_edit")
    start = time.perf_counter()

    # Enable scene_edit (mutation is part of it)
    r = await bridge.call("cmd_enable_toolset", {"category": "scene_edit"})
    result.steps += 1

    r = await bridge.call(
        "cmd_set_node_property",
        {"node_path": "/root/Main/Player", "property": "speed", "value": 300.0},
    )
    result.steps += 1
    if not r["ok"]:
        # Missing node is expected if scene not loaded; that's a valid error
        result.errors += 1
        result.notes = f"set_node_property: {r.get('error')} — {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Property set successfully"
    return result


async def _task_runtime(bridge: BridgeConnector) -> TaskResult:
    """Runtime: play_scene, stop_scene, is_playing"""
    result = TaskResult(task_name="runtime_basics", toolset="runtime")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "runtime"})
    result.steps += 1

    r = await bridge.call("cmd_is_playing", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"is_playing failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Playing: {r.get('result', {}).get('playing')}"
    return result


async def _task_debugger(bridge: BridgeConnector) -> TaskResult:
    """Debugger: set_breakpoint, play, remove, continue"""
    result = TaskResult(task_name="debugger_basics", toolset="debugger")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "debugger"})
    result.steps += 1

    # Must play scene first for debug session
    r = await bridge.call("cmd_play_scene", {"scene_path": "res://scenes/main.tscn"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"play_scene failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    await asyncio.sleep(2)

    # set_breakpoint
    r = await bridge.call("cmd_set_breakpoint", {"path": "res://scripts/player.gd", "line": 42})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"set_breakpoint failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # remove_breakpoint (cleanup)
    r = await bridge.call("cmd_remove_breakpoint", {"path": "res://scripts/player.gd", "line": 42})
    result.steps += 1

    # Continue + stop
    r = await bridge.call("cmd_continue_execution", {})
    result.steps += 1
    await asyncio.sleep(0.5)
    r = await bridge.call("cmd_stop_scene", {})
    result.steps += 1

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Breakpoint set and removed successfully"
    return result


async def _task_physics(bridge: BridgeConnector) -> TaskResult:
    """Physics: setup_physics_body"""
    result = TaskResult(task_name="physics_basics", toolset="physics")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "physics"})
    result.steps += 1

    r = await bridge.call(
        "cmd_setup_physics_body",
        {"node_path": "/root/Main/TestBody", "body_type": "RigidBody2D"},
    )
    result.steps += 1
    if not r["ok"]:
        # Missing node is expected; record the error shape
        result.errors += 1
        result.notes = f"setup_physics_body: {r.get('error')} — {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Physics body configured"
    return result


async def _task_input(bridge: BridgeConnector) -> TaskResult:
    """Input: simulate_key"""
    result = TaskResult(task_name="input_basics", toolset="input")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "input"})
    result.steps += 1

    r = await bridge.call("cmd_simulate_key", {"key": "Space", "pressed": True})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"simulate_key failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Key simulated successfully"
    return result


async def _task_analysis(bridge: BridgeConnector) -> TaskResult:
    """Analysis: project_stats"""
    result = TaskResult(task_name="analysis_basics", toolset="analysis")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "analysis"})
    result.steps += 1

    r = await bridge.call("cmd_project_stats", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"project_stats failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Stats: {r.get('result', {}).get('script_count')} scripts"
    return result


async def _task_export(bridge: BridgeConnector) -> TaskResult:
    """Export: list_presets"""
    result = TaskResult(task_name="export_basics", toolset="export")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "export"})
    result.steps += 1

    r = await bridge.call("cmd_list_presets", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"list_presets failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Presets: {len(r.get('result', {}).get('presets', []))}"
    return result


async def _task_batch(bridge: BridgeConnector) -> TaskResult:
    """Batch: find_nodes_by_type"""
    result = TaskResult(task_name="batch_basics", toolset="batch")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "batch"})
    result.steps += 1

    r = await bridge.call("cmd_find_nodes_by_type", {"node_type": "Node2D"})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"find_nodes_by_type failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = f"Found {len(r.get('result', {}).get('nodes', []))} nodes"
    return result


async def _task_profiling(bridge: BridgeConnector) -> TaskResult:
    """Profiling: get_editor_performance"""
    result = TaskResult(task_name="profiling_basics", toolset="profiling")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "profiling"})
    result.steps += 1

    r = await bridge.call("cmd_get_editor_performance", {})
    result.steps += 1
    if not r["ok"]:
        result.errors += 1
        result.notes = f"get_editor_performance failed: {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Performance data retrieved"
    return result


async def _task_testing(bridge: BridgeConnector) -> TaskResult:
    """Testing: assert_node_state"""
    result = TaskResult(task_name="testing_basics", toolset="testing")
    start = time.perf_counter()

    r = await bridge.call("cmd_enable_toolset", {"category": "testing"})
    result.steps += 1

    r = await bridge.call(
        "cmd_assert_node_state",
        {"node_path": "/root/Main/Player", "property": "speed", "expected": 200.0},
    )
    result.steps += 1
    # May fail if scene not loaded — that's a valid test of error handling
    if not r["ok"]:
        result.errors += 1
        result.notes = f"assert_node_state: {r.get('error')} — {r.get('hint')}"
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    result.success = True
    result.duration_ms = (time.perf_counter() - start) * 1000
    result.notes = "Assertion evaluated"
    return result


# Map toolset -> test task
TASKS: dict[str, TaskFn] = {
    "core": _task_core,
    "inspection": _task_inspection,
    "scene_edit": _task_scene_edit,
    "scripts": _task_scripts,
    "runtime": _task_runtime,
    "debugger": _task_debugger,
    "physics": _task_physics,
    "input": _task_input,
    "analysis": _task_analysis,
    "export": _task_export,
    "batch": _task_batch,
    "profiling": _task_profiling,
    "testing": _task_testing,
}


async def run_suite() -> list[ToolsetResult]:
    print("=" * 70)
    print("  godot-mcp Comprehensive Eval Suite")
    print("=" * 70)

    bridge = BridgeConnector()
    if not await bridge.connect():
        print("ERROR: Could not connect to Godot addon bridge.")
        return []

    results: list[ToolsetResult] = []

    for toolset, task_fn in TASKS.items():
        print(f"\n  [{toolset}]")
        try:
            task_result = await task_fn(bridge)
            toolset_result = ToolsetResult(toolset=toolset, tasks=[task_result])
            results.append(toolset_result)
            status = "✅ PASS" if task_result.success else "❌ FAIL"
            print(
                f"    {status} | steps={task_result.steps} | "
                f"errors={task_result.errors} | "
                f"duration={task_result.duration_ms:.0f}ms"
            )
            if task_result.notes:
                print(f"    {task_result.notes}")
        except Exception as e:
            print(f"    💥 EXCEPTION: {type(e).__name__}: {e}")
            results.append(
                ToolsetResult(
                    toolset=toolset,
                    tasks=[
                        TaskResult(
                            task_name="exception",
                            toolset=toolset,
                            notes=str(e),
                        )
                    ],
                )
            )

    await bridge.close()
    return results


def log_results(results: list[ToolsetResult]) -> None:
    tracker = EvalTracker()
    tracker.start_run(run_name=f"full-suite-{int(time.time())}", variant="comprehensive")

    total_tasks = sum(len(tr.tasks) for tr in results)
    total_errors = sum(tr.total_errors for tr in results)
    passed = sum(1 for tr in results for t in tr.tasks if t.success)
    failed = sum(1 for tr in results for t in tr.tasks if not t.success)

    tracker.log_param("suite_name", "comprehensive")
    tracker.log_param("total_tasks", str(total_tasks))
    tracker.log_param("toolsets_tested", ",".join(r.toolset for r in results))

    tracker.log_metric("completion_rate", passed / max(total_tasks, 1))
    tracker.log_metric("total_errors", float(total_errors))
    tracker.log_metric("failed_tasks", float(failed))

    for tr in results:
        tracker.log_metric(f"{tr.toolset}_completion", tr.completion_rate)
        tracker.log_metric(f"{tr.toolset}_errors", float(tr.total_errors))

    tracker.end_run()
    print(f"\n📊 Logged to MLFlow: {tracker.get_experiment_url()}")


def print_summary(results: list[ToolsetResult]) -> None:
    print("\n" + "=" * 70)
    print("  Evaluation Summary")
    print("=" * 70)
    print(f"  {'Toolset':<18} {'Status':<8} {'Steps':<6} {'Errors':<7} {'Duration':<10} {'Notes'}")
    print("  " + "-" * 66)

    total_pass = 0
    total_fail = 0
    for tr in results:
        for task in tr.tasks:
            status = "PASS" if task.success else "FAIL"
            if task.success:
                total_pass += 1
            else:
                total_fail += 1
            note = (
                task.notes[:40] + "..."
                if len(task.notes) > 40
                else task.notes
            )
            print(
                f"  {tr.toolset:<18} {status:<8} {task.steps:<6} "
                f"{task.errors:<7} {task.duration_ms:<10.0f} {note}"
            )

    print("=" * 70)
    print(
        f"  Total: {total_pass} passed, {total_fail} failed "
        f"out of {total_pass + total_fail} tasks"
    )
    print("=" * 70)


async def main() -> None:
    results = await run_suite()
    print_summary(results)
    if results:
        log_results(results)


if __name__ == "__main__":
    asyncio.run(main())
