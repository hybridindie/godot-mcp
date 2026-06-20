"""Eval representativeness labelling (#197).

The LLM eval agents (OllamaAgent, CloudAgent) execute tool calls by sending
``cmd_*`` envelopes straight to the addon bridge, bypassing the FastMCP server's
safety classes, preconditions, dry_run/confirm, approval webhook, and toolset
gating. Their runs are therefore NOT representative of a server-mediated client.
Until the path is migrated through the server, runs must be explicitly labelled
addon-direct / non-representative in their MLflow traces and console output.
"""

from __future__ import annotations

from typing import Any, cast

from evals.mlflow_tracker import EvalTracker
from evals.representativeness import (
    EXECUTION_PATH_ADDON_DIRECT,
    REPRESENTATIVENESS_BANNER,
    representativeness_params,
)


def test_representativeness_params_mark_addon_direct() -> None:
    params = representativeness_params()
    assert params["execution_path"] == EXECUTION_PATH_ADDON_DIRECT
    assert params["execution_path"] == "addon_direct"
    # Machine-readable "not representative" flag, string-valued for MLflow params.
    assert params["agent_representative"] == "false"


def test_banner_warns_it_bypasses_server_safety() -> None:
    lowered = REPRESENTATIVENESS_BANNER.lower()
    assert "addon-direct" in lowered
    assert "not" in lowered and "representative" in lowered


class _FakeTracker:
    """Records log_param calls; no-ops the rest of the EvalTracker surface."""

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}

    def start_run(self, run_name: str | None = None, variant: str = "baseline") -> None:
        return None

    def log_param(self, key: str, value: Any) -> None:
        self.params[key] = value

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        return None

    def end_run(self, status: str = "FINISHED") -> None:
        return None


def test_log_results_labels_run_non_representative(capsys: Any) -> None:
    from evals.llm_eval_v2 import log_results

    tracker = _FakeTracker()
    # Empty results still logs run-level params (provider/model/... + labels).
    log_results(
        [],
        variant="t",
        model="m",
        provider="anthropic",
        tracker=cast(EvalTracker, tracker),
    )

    assert tracker.params["execution_path"] == "addon_direct"
    assert tracker.params["agent_representative"] == "false"
    # The non-representativeness is also surfaced in console output.
    assert "addon-direct" in capsys.readouterr().out.lower()
