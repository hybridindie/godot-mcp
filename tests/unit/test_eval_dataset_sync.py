"""Unit tests for syncing tool-desc eval tasks into a GenAI dataset (#183).

sqlite-backed and fully offline — no calls to the live MLflow server.
"""

from __future__ import annotations

from pathlib import Path

import mlflow
import pytest

from evals.dataset_sync import sync_dataset, to_records

_PROMPTS = {
    "inspect_scene_tree": "Get the full scene tree and report Sprite2D count.",
    "create_player": "Create a CharacterBody2D named Player.",
}
_EXPECTED = {
    "inspect_scene_tree": "get_scene_tree",
    "create_player": "create_node",
}


def test_to_records_maps_prompt_and_expected_tool() -> None:
    records = to_records(_PROMPTS, _EXPECTED)
    assert len(records) == 2
    by_task = {r["tags"]["task_name"]: r for r in records}

    r = by_task["inspect_scene_tree"]
    assert r["inputs"] == {"prompt": "Get the full scene tree and report Sprite2D count."}
    assert r["expectations"] == {"expected_first_tool": "get_scene_tree"}

    # A task with no expected tool still produces a valid record.
    extra = to_records({"x": "do x"}, {})
    assert extra[0]["expectations"]["expected_first_tool"] is None


def test_sync_noop_without_tracking_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    assert (
        sync_dataset("x", task_prompts=_PROMPTS, expected_first_tools=_EXPECTED) is None
    )


def test_sync_registers_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    ds = sync_dataset(
        "godot-mcp-tool-desc",
        experiment="td-exp",
        tracking_uri=uri,
        task_prompts=_PROMPTS,
        expected_first_tools=_EXPECTED,
    )
    assert ds is not None

    from mlflow.genai.datasets import search_datasets

    mlflow.set_tracking_uri(uri)
    exp = mlflow.get_experiment_by_name("td-exp")
    assert exp is not None
    found = [
        d
        for d in search_datasets(experiment_ids=[exp.experiment_id])
        if getattr(d, "name", "") == "godot-mcp-tool-desc"
    ]
    assert len(found) == 1
