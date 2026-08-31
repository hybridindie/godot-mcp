"""Eval representativeness labelling (#197).

The eval agents (OllamaAgent, CloudAgent) execute tool calls by sending
``cmd_*`` envelopes straight to the addon bridge, bypassing the FastMCP
server's safety classes, preconditions, dry_run/confirm, the approval
webhook, and toolset gating. Their runs are therefore NOT representative
of a server-mediated client.

The MLflow run-params label moved to godot-agents with the MLflow
decoupling (#378); the console banner must still prefix every
``run_llm_suite`` run (both llm_eval_v2 and cross_model_compare) so
results are never mistaken for server-mediated behaviour.
"""

from __future__ import annotations

import pytest

from evals import llm_eval_v2
from evals.llm_eval_v2 import REPRESENTATIVENESS_BANNER, run_llm_suite


def test_banner_text_states_addon_direct_and_non_representative() -> None:
    lowered = REPRESENTATIVENESS_BANNER.lower()
    assert "addon-direct" in lowered
    assert "not" in lowered and "representative" in lowered


async def test_run_llm_suite_prefixes_banner(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The banner prefixes the run even when the bridge is unreachable."""

    class _DeadBridge:
        async def connect(self) -> bool:
            return False

    monkeypatch.setattr(llm_eval_v2, "BridgeConnector", _DeadBridge)
    results = await run_llm_suite()
    assert results == []
    out = capsys.readouterr().out.lower()
    assert "addon-direct" in out
    assert "not representative" in out


def test_banner_has_no_mlflow_coupling() -> None:
    """The banner is pure console output — no tracker, no MLflow params."""
    assert isinstance(REPRESENTATIVENESS_BANNER, str)
    assert not hasattr(llm_eval_v2, "representativeness_params")
    assert not hasattr(llm_eval_v2, "EvalTracker")