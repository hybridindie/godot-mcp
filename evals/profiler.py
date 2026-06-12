"""Per-tool latency profiler for bridge calls.

Collects timing data from both the Python bridge round-trip and (future)
Godot-side handler durations. Produces summary stats for inclusion in eval
reports and MLFlow logging.

Usage:
    profiler = ToolProfiler()
    profiler.record("cmd_ping", latency_ms=12.3)
    profiler.record("cmd_create_node", latency_ms=145.6, ok=True)
    report = profiler.summary()
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolProfiler:
    """Aggregate timing and outcome stats per tool."""

    _calls: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _compressions: list[dict[str, int]] = field(default_factory=list)

    def record(self, tool: str, latency_ms: float, ok: bool = True) -> None:
        """Log a single tool invocation."""
        self._calls.setdefault(tool, []).append({"latency_ms": latency_ms, "ok": ok})

    def record_compression(self, before_chars: int, after_chars: int) -> None:
        """Log a history-compression event (issue #148)."""
        self._compressions.append({"before_chars": before_chars, "after_chars": after_chars})

    def compression_savings(self) -> dict[str, int]:
        """Chars saved by history compression (≈4 chars/token estimate)."""
        saved = sum(c["before_chars"] - c["after_chars"] for c in self._compressions)
        return {
            "compressions": len(self._compressions),
            "chars_saved": saved,
            "est_tokens_saved": saved // 4,
        }

    def summary(self) -> dict[str, dict[str, float | int]]:
        """Return per-tool summary: count, mean, median, p95, min, max, error_rate."""
        out: dict[str, dict[str, float | int]] = {}
        for tool, entries in self._calls.items():
            latencies = [e["latency_ms"] for e in entries]
            errors = sum(1 for e in entries if not e["ok"])
            out[tool] = {
                "count": len(entries),
                "mean_ms": round(statistics.mean(latencies), 2),
                "median_ms": round(statistics.median(latencies), 2),
                "min_ms": round(min(latencies), 2),
                "max_ms": round(max(latencies), 2),
                "error_rate": round(errors / len(entries), 3),
            }
            if len(latencies) >= 2:
                idx = max(0, math.ceil(len(latencies) * 0.95) - 1)
                out[tool]["p95_ms"] = round(sorted(latencies)[idx], 2)
        return out

    def overall(self) -> dict[str, float | int]:
        """Aggregate across all tools."""
        all_entries = [e for entries in self._calls.values() for e in entries]
        if not all_entries:
            return {"total_calls": 0, "mean_ms": 0.0}
        latencies = [e["latency_ms"] for e in all_entries]
        errors = sum(1 for e in all_entries if not e["ok"])
        return {
            "total_calls": len(all_entries),
            "mean_ms": round(statistics.mean(latencies), 2),
            "median_ms": round(statistics.median(latencies), 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "error_rate": round(errors / len(all_entries), 3),
        }

    def slow_tools(self, threshold_ms: float = 500.0) -> list[str]:
        """Return tools whose mean latency exceeds the threshold."""
        summary = self.summary()
        return [
            tool
            for tool, stats in summary.items()
            if stats.get("mean_ms", 0) > threshold_ms
        ]

    def reset(self) -> None:
        """Clear all recorded data."""
        self._calls.clear()
        self._compressions.clear()
