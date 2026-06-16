"""Unit tests for the eval MLflow tracker (issue #181).

Pins the SDK-backed behavior of ``evals.mlflow_tracker.EvalTracker`` against a
local ``sqlite:///`` tracking store so the suite stays fully offline — no calls
to the live ``mlflow.johndstudios.net`` server. These tests are RED against the
old ``curl``-over-``subprocess`` implementation, which ignored
``MLFLOW_TRACKING_URI`` and could only talk to the hardcoded HTTPS endpoint.
"""

from __future__ import annotations

from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient

from evals.mlflow_tracker import EvalTracker


def _sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'mlflow.db'}"


def test_tracker_logs_run_to_sqlite_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full start→log→end cycle records to a local SDK-backed store."""
    monkeypatch.chdir(tmp_path)  # keep any relative artifact dirs out of the repo
    uri = _sqlite_uri(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)

    tracker = EvalTracker(experiment_name="Godot AI")
    run = tracker.start_run(run_name="unit-test", variant="baseline")
    tracker.log_metric("score", 0.9)
    tracker.log_param("model", "qwen")
    tracker.log_artifact_text("notes.txt", "hello world")
    tracker.end_run()

    client = MlflowClient(tracking_uri=uri)

    exp = client.get_experiment_by_name("Godot AI")
    assert exp is not None, "tracker must create/use the 'Godot AI' experiment"

    fetched = client.get_run(run.run_id)
    assert fetched.info.experiment_id == exp.experiment_id
    assert fetched.data.metrics["score"] == 0.9
    assert fetched.data.params["model"] == "qwen"
    assert fetched.data.params["variant"] == "baseline"
    assert fetched.info.status == "FINISHED"


def test_log_artifact_text_writes_a_real_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """log_artifact_text must persist a real artifact file, not a truncated param."""
    monkeypatch.chdir(tmp_path)
    uri = _sqlite_uri(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)

    long_text = "x" * 5000  # exceeds the old 250-char param truncation hack

    tracker = EvalTracker(experiment_name="Godot AI")
    run = tracker.start_run(run_name="artifact-test")
    tracker.log_artifact_text("report.txt", long_text)
    tracker.end_run()

    client = MlflowClient(tracking_uri=uri)
    artifact_paths = [f.path for f in client.list_artifacts(run.run_id)]
    assert "report.txt" in artifact_paths

    fetched = client.get_run(run.run_id)
    # The full text is in the artifact, not stuffed into a truncated param.
    assert "artifact_report.txt" not in fetched.data.params

    local = mlflow.artifacts.download_artifacts(
        run_id=run.run_id, artifact_path="report.txt", tracking_uri=uri
    )
    with open(local, encoding="utf-8") as fh:
        assert fh.read() == long_text


def test_tracker_honors_tracking_uri_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tracker must route to MLFLOW_TRACKING_URI (offline), not a hardcoded host."""
    monkeypatch.chdir(tmp_path)
    uri = _sqlite_uri(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)

    tracker = EvalTracker(experiment_name="Godot AI")
    run = tracker.start_run(run_name="env-test")
    tracker.end_run()

    # Run is retrievable from the configured store with no network access.
    client = MlflowClient(tracking_uri=uri)
    assert client.get_run(run.run_id).info.run_id == run.run_id
