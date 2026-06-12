#!/usr/bin/env python3
"""Performance regression test for batch_set_property and find_nodes_by_type.

Run this when the Godot editor is open with the vampire example project:
    python -m evals.batch_perf_test

Measures latency before and after the optimization fixes in:
- command_router.gd: _property_type cache
- batch.gd: skip UndoRedo for large batches (>20 nodes)
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from evals.agent_suite_v2 import BridgeConnector  # noqa: E402


async def test_batch_performance() -> dict:
    """Measure batch_set_property and find_nodes_by_type latency."""
    bridge = BridgeConnector()
    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge.")
        return {}

    results: dict = {}

    try:
        # Create test nodes
        for i in range(5):
            r = await bridge.call(
                "cmd_create_node",
                {"parent_path": ".", "node_type": "Node2D", "name": f"PerfTest{i}"},
            )
            print(f"  create PerfTest{i}: ok={r.get('ok')}")
            await asyncio.sleep(0.2)

        # Test batch_set_property with 5 nodes (small batch, uses UndoRedo)
        print("\n--- batch_set_property (5 nodes, UndoRedo path) ---")
        t0 = time.perf_counter()
        r = await bridge.call(
            "cmd_batch_set_property",
            {
                "node_paths": [f"PerfTest{i}" for i in range(5)],
                "property": "position",
                "value": {"x": 100, "y": 200},
            },
        )
        dur_ms = round((time.perf_counter() - t0) * 1000, 2)
        print(
            f"  result: ok={r.get('ok')}, dur={dur_ms}ms, "
            f"applied={r.get('result', {}).get('count')}"
        )
        results["batch_5_nodes_ms"] = dur_ms

        # Test find_nodes_by_type
        print("\n--- find_nodes_by_type (Node2D) ---")
        t0 = time.perf_counter()
        r = await bridge.call(
            "cmd_find_nodes_by_type",
            {"parent_path": ".", "type": "Node2D", "recursive": True},
        )
        dur_ms = round((time.perf_counter() - t0) * 1000, 2)
        print(
            f"  result: ok={r.get('ok')}, dur={dur_ms}ms, "
            f"count={r.get('result', {}).get('count')}"
        )
        results["find_nodes_by_type_ms"] = dur_ms

        # Cleanup
        for i in range(5):
            await bridge.call(
                "cmd_delete_node",
                {"node_path": f"PerfTest{i}", "confirm": True},
            )

    finally:
        await bridge.close()

    print("\n--- Summary ---")
    for k, v in results.items():
        print(f"  {k}: {v}ms")
    return results


if __name__ == "__main__":
    asyncio.run(test_batch_performance())
