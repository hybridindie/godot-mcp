#!/usr/bin/env python3
"""MLflow tracking client wrapper for godot-mcp evals.

Thin wrapper over the MLflow Python SDK (``MlflowClient``) that records eval
runs to the unified **"Godot AI"** experiment shared with the godot-agents
project.

Routing:
    The tracking server is taken from ``MLFLOW_TRACKING_URI`` when set,
    otherwise it falls back to the shared instance below. Tests point it at a
    local ``sqlite:///`` store so the suite stays fully offline.

History:
    Earlier revisions delegated every call to ``curl`` via ``subprocess`` to
    work around a local socket failure to ``192.168.0.20:443``. That networking
    issue is resolved (2026-06-16), so this now uses the SDK directly, which
    also unlocks MLflow 3.x GenAI features (tracing, datasets, judges).

Usage:
    from evals.mlflow_tracker import EvalTracker
    tracker = EvalTracker()
    tracker.start_run("debugger-desc-eval-v1")
    tracker.log_metric("completion_rate", 0.85)
    tracker.log_param("variant", "baseline")
    tracker.end_run()
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from mlflow import MlflowClient

logger = logging.getLogger(__name__)

# Shared instance used when MLFLOW_TRACKING_URI is unset.
DEFAULT_TRACKING_URI = "https://mlflow.johndstudios.net"


@dataclass
class EvalRun:
    """A single evaluation run."""

    run_id: str
    experiment_id: str
    variant: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)


class EvalTracker:
    """Track godot-mcp eval runs in the unified "Godot AI" MLflow experiment."""

    def __init__(self, experiment_name: str = "Godot AI") -> None:
        self._experiment_name = experiment_name
        self._tracking_uri = os.environ.get("MLFLOW_TRACKING_URI") or DEFAULT_TRACKING_URI
        self._client = MlflowClient(tracking_uri=self._tracking_uri)
        self._experiment_id: str | None = None
        self._run: EvalRun | None = None
        self._ensure_experiment()

    def _ensure_experiment(self) -> None:
        """Resolve the experiment id, creating the experiment if it doesn't exist."""
        exp = self._client.get_experiment_by_name(self._experiment_name)
        if exp is not None:
            self._experiment_id = exp.experiment_id
        else:
            self._experiment_id = self._client.create_experiment(self._experiment_name)

    def start_run(self, run_name: str | None = None, variant: str = "baseline") -> EvalRun:
        """Start a new evaluation run."""
        if self._experiment_id is None:
            raise RuntimeError("Experiment not initialized")
        run_name = run_name or f"eval-{int(time.time())}"
        run = self._client.create_run(
            experiment_id=self._experiment_id, run_name=run_name
        )
        self._run = EvalRun(
            run_id=run.info.run_id,
            experiment_id=self._experiment_id,
            variant=variant,
        )
        self.log_param("variant", variant)
        self.log_param("experiment_name", self._experiment_name)
        return self._run

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        """Log a numeric metric for the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        self._client.log_metric(
            self._run.run_id,
            key,
            value,
            timestamp=int(time.time() * 1000),
            step=step or 0,
        )
        self._run.metrics[key] = value

    def log_param(self, key: str, value: str) -> None:
        """Log a string parameter for the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        self._client.log_param(self._run.run_id, key, value)
        self._run.params[key] = value

    def log_artifact_text(self, filename: str, content: str) -> None:
        """Log ``content`` as a real text artifact for the current run.

        Artifact upload depends on the server's artifact store. The shared
        instance uses S3 (``s3://mlflow/...``), which needs ``boto3`` plus AWS
        credentials in the environment. If the upload fails (e.g. no creds), we
        warn and continue rather than abort the eval run — metrics/params are
        already recorded and matter most.
        """
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        try:
            self._client.log_text(self._run.run_id, content, filename)
        except Exception as exc:  # pragma: no cover - depends on artifact store/creds
            logger.warning(
                "MLflow artifact upload failed for %r (run %s); continuing. "
                "S3 artifact stores need boto3 + AWS credentials. Error: %s",
                filename,
                self._run.run_id,
                exc,
            )

    def end_run(self, status: str = "FINISHED") -> EvalRun:
        """End the current run."""
        if self._run is None:
            raise RuntimeError("No active run. Call start_run() first.")
        self._client.set_terminated(self._run.run_id, status)
        run = self._run
        self._run = None
        return run

    @property
    def active_run(self) -> EvalRun | None:
        return self._run

    def get_experiment_url(self) -> str:
        """Return the MLflow UI URL for the experiment."""
        base = self._tracking_uri.rstrip("/")
        return f"{base}/#/experiments/{self._experiment_id}"
