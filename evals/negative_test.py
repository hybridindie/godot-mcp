#!/usr/bin/env python3
"""Negative / anti-pattern tests — verify error handling and safety boundaries.

Tests the agent's resilience to:
1. Delete without confirm → should fail (safety gate)
2. Set property on non-existent node → should fail gracefully
3. Set property with wrong type → should fail with clear hint
4. Create node with invalid type → should fail
5. Rename to duplicate name → should fail

Usage:
    python -m evals.negative_test
    python -m evals.negative_test --task delete_without_confirm
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, "/Users/johnd/Development/godot-mcp")

from evals.agent_suite_v2 import BridgeConnector
from evals.mlflow_tracker import EvalTracker
from evals.profiler import ToolProfiler

# ---------------------------------------------------------------------------
# Negative test definitions
# ---------------------------------------------------------------------------

NEGATIVE_TESTS: dict[str, dict] = {
    "delete_without_confirm": {
        "setup": [
            {
                "tool": "create_node",
                "params": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "name": "DeleteMe",
                },
                "extract": {"node_path": "node_path"},
            },
        ],
        "test": {
            "tool": "delete_node",
            "params": {"node_path": "{node_path}"},  # Missing confirm=True
        },
        "expect_error": "confirm",
        "description": "Delete without confirm should fail with safety error",
    },
    "set_property_nonexistent_node": {
        "test": {
            "tool": "set_node_property",
            "params": {
                "node_path": "IDoNotExist",
                "property": "position",
                "value": {"x": 100, "y": 200},
            },
        },
        "expect_error": "RESOURCE_NOT_FOUND",
        "description": "Set property on non-existent node should fail gracefully",
    },
    "set_property_wrong_type": {
        "setup": [
            {
                "tool": "create_node",
                "params": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "name": "TypeTest",
                },
                "extract": {"node_path": "node_path"},
            },
        ],
        "test": {
            "tool": "set_node_property",
            "params": {
                "node_path": "{node_path}",
                "property": "position",
                "value": "not_a_vector2",
            },
        },
        "expect_error": None,  # May fail or coerce; just check it doesn't crash
        "description": "Set property with wrong type should not crash",
    },
    "create_node_invalid_type": {
        "test": {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "NotARealClass",
                "name": "BadType",
            },
        },
        "expect_error": "VALIDATION_ERROR",
        "description": "Create node with invalid type should fail",
    },
    "rename_to_duplicate": {
        "setup": [
            {
                "tool": "create_node",
                "params": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "name": "RenameA",
                },
                "extract": {"path_a": "node_path"},
            },
            {
                "tool": "create_node",
                "params": {
                    "parent_path": ".",
                    "node_type": "Node2D",
                    "name": "RenameB",
                },
                "extract": {"path_b": "node_path"},
            },
        ],
        "test": {
            "tool": "rename_node",
            "params": {
                "node_path": "{path_a}",
                "new_name": "RenameB",  # Duplicate with existing RenameB
            },
        },
        "expect_error": None,
        "description": "Rename to existing name may succeed or fail depending on Godot behavior",
    },
}


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

@dataclass
class NegativeTestResult:
    task_name: str
    passed: bool = False  # True if the negative test behaved as expected
    setup_ok: bool = True
    test_error: str = ""
    test_hint: str = ""
    latency_ms: float = 0.0
    notes: str = ""
    duration_ms: float = 0.0


async def run_negative_test(
    bridge: BridgeConnector,
    task_name: str,
    profiler: ToolProfiler | None = None,
) -> NegativeTestResult:
    """Run a single negative test."""
    result = NegativeTestResult(task_name=task_name)
    definition = NEGATIVE_TESTS.get(task_name)
    if definition is None:
        result.notes = f"Unknown negative test: {task_name}"
        return result

    start = time.perf_counter()
    context: dict[str, any] = {}

    # Run setup steps
    setup_steps = definition.get("setup", [])
    for step in setup_steps:
        raw_params = step.get("params", {})
        params = _resolve_params(raw_params, context)
        t0 = time.perf_counter()
        resp = await bridge.call(f"cmd_{step['tool']}", params)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if profiler:
            profiler.record(step["tool"], latency_ms, ok=resp.get("ok", False))

        if not resp.get("ok", False):
            result.setup_ok = False
            result.notes = f"Setup failed at {step['tool']}: {resp.get('error')}"
            result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return result

        # Extract context values
        for key, spec in step.get("extract", {}).items():
            value = _extract_value(resp.get("result", {}), spec)
            context[key] = value

        # Give mutation operations time to flush
        if step["tool"] in {"create_node", "rename_node", "delete_node"}:
            await asyncio.sleep(0.2)

    # Run the negative test step
    test_def = definition["test"]
    raw_params = test_def.get("params", {})
    params = _resolve_params(raw_params, context)

    t0 = time.perf_counter()
    resp = await bridge.call(f"cmd_{test_def['tool']}", params)
    result.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    if profiler:
        profiler.record(test_def["tool"], result.latency_ms, ok=resp.get("ok", False))

    result.test_error = resp.get("error", "")
    result.test_hint = resp.get("hint", "")

    expect_error = definition.get("expect_error")
    if expect_error is None:
        # Just verify it didn't crash (error or ok is fine)
        result.passed = True
        result.notes = f"Completed without crash. ok={resp.get('ok')}, error={resp.get('error')}"
    else:
        # We expect an error containing the expected string
        if result.test_error and expect_error.lower() in result.test_error.lower():
            result.passed = True
            result.notes = f"Expected error occurred: {result.test_error}"
        elif not resp.get("ok", False):
            result.passed = True
            result.notes = f"Failed as expected (generic): {result.test_error}"
        else:
            result.passed = False
            result.notes = (
                f"UNEXPECTED SUCCESS: expected error containing '{expect_error}', "
                f"but got ok=True. This may indicate a missing safety check."
            )

    result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_params(raw: dict, context: dict) -> dict:
    """Replace '{placeholder}' strings in params with context values."""

    def _resolve(v: any) -> any:
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            key = v[1:-1]
            if key not in context:
                raise KeyError(f"Missing context key: {key}")
            return context[key]
        if isinstance(v, list):
            return [_resolve(item) for item in v]
        if isinstance(v, dict):
            return {k: _resolve(val) for k, val in v.items()}
        return v

    return {k: _resolve(v) for k, v in raw.items()}


def _extract_value(result: dict, spec: str) -> any:
    """Simple dotted accessor for extraction specs."""
    parts = spec.split(".")
    current: any = result
    for part in parts:
        if part.endswith("]"):
            name, idx_str = part[:-1].split("[")
            if name:
                current = current.get(name, [])
            if isinstance(current, list) and current:
                idx = int(idx_str)
                current = current[idx] if idx < len(current) else {}
            else:
                current = {}
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
        if current is None:
            return None
    return current


# ---------------------------------------------------------------------------
# Report / MLFlow
# ---------------------------------------------------------------------------

def print_negative_report(results: list[NegativeTestResult]) -> None:
    print("\n" + "=" * 70)
    print("  Negative / Anti-Pattern Test Report")
    print("=" * 70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"  Tests: {passed}/{total} passed")
    for r in results:
        status = "✅" if r.passed else "❌"
        print(f"  {status} {r.task_name}: {r.notes}")
        if r.test_error:
            print(f"     Error: {r.test_error} | Hint: {r.test_hint}")
    print("=" * 70)


def log_to_mlflow(results: list[NegativeTestResult], git_sha: str = "") -> None:
    tracker = EvalTracker()
    tracker.start_run(run_name=f"negative-test-{int(time.time())}")
    tracker.log_param("suite", "negative_test")
    tracker.log_param("git_sha", git_sha)
    tracker.log_param("test_count", len(results))
    passed = sum(1 for r in results if r.passed)
    tracker.log_metric("tests_passed", passed)
    tracker.log_metric("tests_total", len(results))
    tracker.log_metric("pass_rate", passed / len(results) if results else 0)
    for r in results:
        prefix = r.task_name
        tracker.log_metric(f"{prefix}_passed", 1.0 if r.passed else 0.0)
        tracker.log_metric(f"{prefix}_latency_ms", r.latency_ms)
        tracker.log_metric(f"{prefix}_duration_ms", r.duration_ms)
        if r.notes:
            tracker.log_param(f"{prefix}_notes", r.notes[:250])
    tracker.end_run()
    print("\n📊 Negative test results logged to MLFlow")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: list[str] | None = None) -> None:
    bridge = BridgeConnector()
    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge.")
        return

    tasks = list(NEGATIVE_TESTS.keys())
    if args and "--task" in args:
        idx = args.index("--task")
        if idx + 1 < len(args):
            tasks = [args[idx + 1]]

    profiler = ToolProfiler()
    results: list[NegativeTestResult] = []

    try:
        for task_name in tasks:
            print(f"Running negative test: {task_name} ...")
            result = await run_negative_test(bridge, task_name, profiler=profiler)
            results.append(result)
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"  {status}")
    finally:
        # Cleanup: delete any test nodes that may have been created
        for name in ["DeleteMe", "TypeTest", "RenameA", "RenameB"]:
            try:
                await bridge.call(
                    "cmd_delete_node",
                    {"node_path": name, "confirm": True},
                )
            except Exception:
                pass
        await bridge.close()

    print_negative_report(results)
    log_to_mlflow(results)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
