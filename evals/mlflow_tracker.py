#!/usr/bin/env python3
"""MLFlow tracking client wrapper for godot-mcp evals.

Works around a local networking issue where Python's socket.connect()
fails to reach 192.168.0.20:443 (Errno 65) but curl succeeds.
All API calls delegate to curl via subprocess.

Usage:
    from evals.mlflow_tracker import EvalTracker
    tracker = EvalTracker()
    tracker.start_run("debugger-desc-eval-v1")
    tracker.log_metric("completion_rate", 0.85)
    tracker.log_param("variant", "baseline")
    tracker.end_run()
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

MLFLOW_BASE = "https://mlflow.johndstudios.net/api/2.0/mlflow"


def _curl(method: str, endpoint: str, payload: dict | None = None) -> dict:
    """Call the MLFlow REST API via curl."""
    url = f"{MLFLOW_BASE}/{endpoint}"
    args = [
        "curl", "-s", "--max-time", "15",
        "-X", method,
        "-H", "Content-Type: application/json",
    ]
    if payload is not None:
        args += ["-d", json.dumps(payload)]
    args.append(url)

    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    # Some endpoints return empty body on success (e.g. log-metric)
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON from MLFlow: {result.stdout[:200]}"
        ) from exc


def _curl_get(endpoint: str, query: dict) -> dict:
    """Call a GET endpoint with query params via curl."""
    qs = "&".join(f"{k}={v}" for k, v in query.items())
    url = f"{MLFLOW_BASE}/{endpoint}?{qs}"
    args = ["curl", "-s", "--max-time", "15", "-X", "GET", url]

    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON from MLFlow: {result.stdout[:200]}"
        ) from exc


@dataclass
class EvalRun:
    """A single evaluation run."""

    run_id: str
    experiment_id: str
    variant: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)


class EvalTracker:
    """Track godot-mcp tool description evaluation experiments in MLFlow."""

    def __init__(self, experiment_name: str = "godot-mcp-tool-desc-eval") -> None:
        self._experiment_name = experiment_name
        self._experiment_id: str | None = None
        self._run: EvalRun | None = None
        self._ensure_experiment()

    def _ensure_experiment(self) -> None:
        """Create the experiment if it doesn't exist."""
        # Try to create
        resp = _curl("POST", "experiments/create", {"name": self._experiment_name})
        if "experiment_id" in resp:
            self._experiment_id = resp["experiment_id"]
            return
        # Already exists — get by name via GET
        resp = _curl_get("experiments/get-by-name", {"experiment_name": self._experiment_name})
        self._experiment_id = resp["experiment"]["experiment_id"]

    def start_run(self, run_name: str | None = None, variant: str = "baseline") -> EvalRun:
        """Start a new evaluation run."""
        if self._experiment_id is None:
            raise RuntimeError("Experiment not initialized")
        run_name = run_name or f"eval-{int(time.time())}"
        resp = _curl(
            "POST",
            "runs/create",
            {"experiment_id": self._experiment_id, "run_name": run_name},
        )
        run_id = resp["run"]["info"]["run_id"]
        self._run = EvalRun(run_id=run_id, experiment_id=self._experiment_id, variant=variant)
        self.log_param("variant", variant)
        self.log_param("experiment_name", self._experiment_name)
        return self._run

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        """Log a numeric metric for the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        payload: dict[str, Any] = {
            "run_id": self._run.run_id,
            "key": key,
            "value": value,
            "timestamp": int(time.time() * 1000),
        }
        if step is not None:
            payload["step"] = step
        _curl("POST", "runs/log-metric", payload)
        self._run.metrics[key] = value

    def log_param(self, key: str, value: str) -> None:
        """Log a string parameter for the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        _curl(
            "POST",
            "runs/log-parameter",
            {"run_id": self._run.run_id, "key": key, "value": value},
        )
        self._run.params[key] = value

    def log_artifact_text(self, filename: str, content: str) -> None:
        """Log a text artifact for the current run."""
        # MLFlow artifact logging requires multipart upload; for now we log the
        # content as a param (truncated to 250 chars to stay within limits).
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        truncated = content[:250] if len(content) > 250 else content
        self.log_param(f"artifact_{filename}", truncated)

    def end_run(self, status: str = "FINISHED") -> EvalRun:
        """End the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        _curl("POST", "runs/update", {"run_id": self._run.run_id, "status": status})
        run = self._run
        self._run = None
        return run

    @property
    def active_run(self) -> EvalRun | None:
        return self._run

    def get_experiment_url(self) -> str:
        """Return the MLFlow UI URL for the experiment."""
        base = MLFLOW_BASE.replace("/api/2.0/mlflow", "")
        return f"{base}/#/experiments/{self._experiment_id}"
