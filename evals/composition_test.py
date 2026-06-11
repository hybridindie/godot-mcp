#!/usr/bin/env python3
"""Cross-tool composition tests — verify output of tool A feeds correctly into tool B.

Tests the "integration" layer of the agent: path format coherence, property type
round-tripping, node lifetime between steps, and multi-tool chain completion.

Chains to test:
1.  get_scene_tree → get_node_properties → set_node_property
2.  get_node_property_list → find_nodes_by_type → batch_set_property
3.  create_node → attach_script → write_script → play_scene → stop_scene
4.  get_script_for_node → read_script → patch_script → get_parse_errors

Usage:
    python -m evals.composition_test
    python -m evals.composition_test --chain inspect_mutate
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from evals.agent_suite_v2 import BridgeConnector
from evals.mlflow_tracker import EvalTracker
from evals.profiler import ToolProfiler

# ---------------------------------------------------------------------------
# Composition chain definitions
# ---------------------------------------------------------------------------

COMPOSITION_CHAINS: dict[str, list[dict]] = {
    "inspect_mutate": [
        {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "Node2D",
                "name": "CompTest",
            },
            "extract": {
                "node_path": "node_path",
            },
        },
        {
            "tool": "set_node_property",
            "params": {
                "node_path": "{node_path}",
                "property": "position",
                "value": {"x": 100, "y": 200},
            },
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "get_node_property_list",
            "params": {"node_path": "{node_path}"},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
    ],
    "find_and_batch": [
        {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "Node2D",
                "name": "BatchA",
            },
            "extract": {"path_a": "node_path"},
        },
        {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "Node2D",
                "name": "BatchB",
            },
            "extract": {"path_b": "node_path"},
        },
        {
            "tool": "batch_set_property",
            "params": {
                "node_paths": ["{path_a}", "{path_b}"],
                "property": "position",
                "value": {"x": 100, "y": 200},
            },
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
    ],
    "create_attach_run": [
        {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "Node2D",
                "name": "ChainPlayer",
            },
            "extract": {
                "node_path": "node_path",
            },
        },
        {
            "tool": "write_script",
            "params": {
                "script_path": "res://test_chain_player.gd",
                "content": "extends Node2D\nfunc _ready():\n    print('hello from chain')\n",
            },
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "attach_script",
            "params": {
                "node_path": "{node_path}",
                "template": "extends Node2D\nfunc _ready(): pass",
                "script_path": "res://test_chain_player.gd",
            },
            "extract": {
                "script_path": "script_path",
            },
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "play_scene",
            "params": {},
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "stop_scene",
            "params": {},
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
    ],
    "script_roundtrip": [
        {
            "tool": "create_node",
            "params": {
                "parent_path": ".",
                "node_type": "Node",
                "name": "ScriptTest",
            },
            "extract": {
                "node_path": "node_path",
            },
        },
        {
            "tool": "write_script",
            "params": {
                "script_path": "res://test_script_roundtrip.gd",
                "content": (
                    "extends Node\n"
                    "var health = 100\n"
                    "func _ready():\n"
                    "    print('starting')\n"
                ),
            },
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "attach_script",
            "params": {
                "node_path": "{node_path}",
                "template": "extends Node\nfunc _ready(): pass",
                "script_path": "res://test_script_roundtrip.gd",
            },
            "extract": {
                "script_path": "script_path",
            },
        },
        {
            "tool": "get_script_for_node",
            "params": {"node_path": "{node_path}"},
            "extract": {
                "read_path": "script_path",
            },
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "read_script",
            "params": {"script_path": "{read_path}"},
            "extract": {
                "original_content": "content",
            },
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "patch_script",
            "params": {
                "script_path": "{script_path}",
                "find": "var health = 100",
                "replace": "var health = 200",
            },
            "extract": {},
            "validate": lambda result, ctx=None: result.get("ok", False),
        },
        {
            "tool": "read_script",
            "params": {"script_path": "{script_path}"},
            "extract": {
                "patched_content": "content",
            },
            "validate": lambda result, ctx=None: (
                result.get("ok", False)
                and "health = 200" in result.get("result", {}).get("content", "")
            ),
        },
    ],
}


# ---------------------------------------------------------------------------
# Composition runner
# ---------------------------------------------------------------------------

@dataclass
class ChainResult:
    chain_name: str
    steps: list[dict] = field(default_factory=list)
    passed: bool = False
    break_index: int = -1  # -1 = all passed
    error: str = ""
    duration_ms: float = 0.0
    latency_profile: dict = field(default_factory=dict)


async def run_chain(
    bridge: BridgeConnector,
    chain_name: str,
    profiler: ToolProfiler | None = None,
    mutation_delay: float = 0.2,
) -> ChainResult:
    """Execute a composition chain, extracting fields between steps."""
    result = ChainResult(chain_name=chain_name)
    chain = COMPOSITION_CHAINS.get(chain_name, [])
    start = time.perf_counter()

    context: dict[str, any] = {}  # extracted values feed forward

    MUTATION_TOOLS = {
        "create_node",
        "delete_node",
        "rename_node",
        "attach_script",
        "set_node_property",
        "batch_set_property",
    }

    for i, step_def in enumerate(chain):
        tool = step_def["tool"]
        raw_params = step_def.get("params", {})
        extract = step_def.get("extract", {})
        validate = step_def.get("validate")

        # Resolve parameter placeholders from context
        params = _resolve_params(raw_params, context)

        call_start = time.perf_counter()
        resp = await bridge.call(f"cmd_{tool}", params)
        latency_ms = round((time.perf_counter() - call_start) * 1000, 2)
        if profiler is not None:
            profiler.record(tool, latency_ms, ok=resp.get("ok", False))

        step_record = {
            "index": i,
            "tool": tool,
            "params": params,
            "ok": resp.get("ok", False),
            "error": resp.get("error"),
            "hint": resp.get("hint"),
            "latency_ms": latency_ms,
        }
        result.steps.append(step_record)

        if not resp.get("ok", False):
            result.break_index = i
            result.error = f"Step {i} ({tool}) failed: {resp.get('error')}"
            return result

        # Extract values for next steps
        for key, spec in extract.items():
            if key == "description":
                continue
            try:
                value = _extract_value(resp.get("result", {}), spec, context)
                context[key] = value
            except Exception as e:
                result.break_index = i
                result.error = f"Extraction failed for '{key}': {e}"
                return result

        # Run validation if provided
        if validate is not None:
            try:
                if not validate(resp, context):
                    result.break_index = i
                    result.error = f"Validation failed at step {i} ({tool})"
                    return result
            except Exception as e:
                result.break_index = i
                result.error = f"Validation exception at step {i}: {e}"
                return result

        # Yield after mutation tools so Godot's EditorUndoRedoManager can flush
        if tool in MUTATION_TOOLS:
            await asyncio.sleep(mutation_delay)

    result.passed = True
    result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_params(raw: dict, context: dict) -> dict:
    """Replace '{placeholder}' strings in params (including nested lists) with context values."""
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


def _extract_value(result: dict, spec: str, context: dict) -> any:
    """Extract a value from a result dict using a simple dotted accessor.

    Supports:
    - "nodes[0].path"  → first node path
    - "properties[0].name" → first property name
    - "{target_node}" → resolved from context
    """
    # If spec references another context key, resolve first
    if spec.startswith("{") and spec.endswith("}"):
        inner = spec[1:-1]
        return context.get(inner, "")

    parts = spec.split(".")
    current: any = result
    for part in parts:
        if part.endswith("]"):
            # array access: e.g. "nodes[0]"
            name, idx_str = part[:-1].split("[")
            if name:
                current = current.get(name, [])
            if isinstance(current, list) and current:
                idx = int(idx_str)
                current = current[idx] if idx < len(current) else {}
            elif isinstance(current, dict):
                current = current
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
# Report / MLFlow logging
# ---------------------------------------------------------------------------

def print_chain_report(results: list[ChainResult]) -> None:
    print("\n" + "=" * 70)
    print("  Cross-Tool Composition Test Report")
    print("=" * 70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"  Chains: {passed}/{total} passed")
    for r in results:
        status = "✅" if r.passed else "❌"
        print(
            f"  {status} {r.chain_name}: {len(r.steps)} steps, "
            f"{r.duration_ms:.0f}ms"
        )
        if not r.passed:
            print(f"     Break at step {r.break_index}: {r.error}")
    print("=" * 70)


def log_to_mlflow(results: list[ChainResult], git_sha: str = "") -> None:
    tracker = EvalTracker()
    tracker.start_run(run_name=f"composition-test-{int(time.time())}")
    tracker.log_param("suite", "composition_test")
    tracker.log_param("git_sha", git_sha)
    tracker.log_param("chain_count", len(results))
    passed = sum(1 for r in results if r.passed)
    tracker.log_metric("chains_passed", passed)
    tracker.log_metric("chains_total", len(results))
    tracker.log_metric("pass_rate", passed / len(results) if results else 0)
    for r in results:
        prefix = r.chain_name
        tracker.log_metric(f"{prefix}_passed", 1.0 if r.passed else 0.0)
        tracker.log_metric(f"{prefix}_steps", len(r.steps))
        tracker.log_metric(f"{prefix}_duration_ms", r.duration_ms)
        if r.latency_profile:
            for tool, stats in r.latency_profile.items():
                tracker.log_metric(f"{prefix}_{tool}_mean_ms", stats.get("mean_ms", 0))
    tracker.end_run()
    print("\n📊 Composition results logged to MLFlow")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: list[str] | None = None) -> None:
    bridge = BridgeConnector()
    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge.")
        return

    chains = list(COMPOSITION_CHAINS.keys())
    if args and "--chain" in args:
        idx = args.index("--chain")
        if idx + 1 < len(args):
            chains = [args[idx + 1]]

    profiler = ToolProfiler()
    results: list[ChainResult] = []

    try:
        for chain_name in chains:
            print(f"Running chain: {chain_name} ...")
            result = await run_chain(bridge, chain_name, profiler=profiler)
            results.append(result)
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"  {status} ({len(result.steps)} steps, {result.duration_ms:.0f}ms)")
            if not result.passed:
                print(f"     Break: {result.error}")
    finally:
        await bridge.close()

    print_chain_report(results)
    log_to_mlflow(results)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
