#!/usr/bin/env python3
"""Register tool-desc eval tasks as an MLflow GenAI dataset in "Godot AI" (#183).

`evals/llm_eval_v2.py` defines the tool-description eval tasks declaratively
(``TASK_PROMPTS`` + ``EXPECTED_FIRST_TOOLS``). This maps them into MLflow GenAI
dataset records and registers them under the unified "Godot AI" experiment so
the tool-desc data lives alongside godot-agents' datasets and judges.

Opt-in: a no-op (returns ``None``) when no tracking URI is configured.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

DEFAULT_EXPERIMENT = "Godot AI"


def to_records(
    task_prompts: dict[str, str],
    expected_first_tools: dict[str, str],
) -> list[dict[str, Any]]:
    """Map tool-desc tasks to GenAI records. Pure and unit-testable.

    Each task -> ``{inputs: {prompt}, expectations: {expected_first_tool}, tags}``.
    """
    records: list[dict[str, Any]] = []
    for task_name, prompt in task_prompts.items():
        records.append(
            {
                "inputs": {"prompt": prompt},
                "expectations": {"expected_first_tool": expected_first_tools.get(task_name)},
                "tags": {"task_name": task_name},
            }
        )
    return records


def sync_dataset(
    name: str,
    *,
    experiment: str = DEFAULT_EXPERIMENT,
    tracking_uri: str | None = None,
    task_prompts: dict[str, str] | None = None,
    expected_first_tools: dict[str, str] | None = None,
) -> Any | None:
    """Register the tool-desc tasks as a GenAI dataset under ``experiment``.

    Idempotent: reuses an existing dataset of the same ``name`` in the experiment.
    Falls back to ``llm_eval_v2``'s task tables when the dicts aren't supplied.
    Returns the dataset, or ``None`` when tracking is not configured.
    """
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        return None

    if task_prompts is None or expected_first_tools is None:
        from evals.llm_eval_v2 import EXPECTED_FIRST_TOOLS, TASK_PROMPTS

        task_prompts = task_prompts or TASK_PROMPTS
        expected_first_tools = expected_first_tools or EXPECTED_FIRST_TOOLS

    import mlflow
    from mlflow.genai.datasets import create_dataset, search_datasets

    mlflow.set_tracking_uri(uri)
    exp = mlflow.set_experiment(experiment)
    records = to_records(task_prompts, expected_first_tools)

    existing = [
        d
        for d in search_datasets(experiment_ids=[exp.experiment_id])
        if getattr(d, "name", "") == name
    ]
    dataset = (
        existing[0] if existing else create_dataset(name=name, experiment_id=[exp.experiment_id])
    )
    dataset.merge_records(records)
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync tool-desc eval tasks into MLflow (Godot AI)."
    )
    parser.add_argument("--name", default="godot-mcp-tool-desc", help="GenAI dataset name")
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT, help="MLflow experiment")
    parser.add_argument("--tracking-uri", default=None, help="MLflow tracking URI (or use env)")
    args = parser.parse_args()

    dataset = sync_dataset(args.name, experiment=args.experiment, tracking_uri=args.tracking_uri)
    if dataset is None:
        print("No MLFLOW_TRACKING_URI configured; nothing synced.")
    else:
        print(f"Synced dataset '{args.name}' into experiment '{args.experiment}'.")


if __name__ == "__main__":
    main()
