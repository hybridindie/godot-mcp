"""Eval representativeness labelling (#197).

The LLM eval agents in this package (``OllamaAgent``, ``CloudAgent``) execute
tool calls by sending ``cmd_*`` envelopes **straight to the addon bridge** (see
``CloudAgent._execute`` / ``OllamaAgent``), bypassing the FastMCP server's
safety classes, preconditions, ``dry_run``/``confirm``, the approval webhook,
and toolset gating. Their results therefore do **not** reflect the safety
behaviour a real, *server-mediated* client experiences (PRD FR3).

Migrating that execution path onto the server (an MCP client/session, switching
from addon ``cmd_*`` param keys to the server tool surface) is tracked as the
representative path; until then, runs are labelled addon-direct /
non-representative so the distinction is explicit in MLflow and console output.

Intentionally out of scope (these *should* stay addon-direct — they test the
bridge/addon contract and perf, not agent-representativeness):
``batch_perf_test.py``, ``composition_test.py``, ``negative_test.py``.
"""

from __future__ import annotations

# Stable, machine-readable execution-path marker for the addon-direct eval path.
EXECUTION_PATH_ADDON_DIRECT = "addon_direct"

# Console banner surfaced alongside addon-direct eval output.
REPRESENTATIVENESS_BANNER = (
    "⚠️  addon-direct eval path: tool calls bypass the FastMCP server's safety "
    "classes / preconditions / dry_run / approval / toolset gating — results are "
    "NOT representative of a server-mediated client (#197)."
)


def representativeness_params() -> dict[str, str]:
    """MLflow params marking a run as addon-direct / non-representative.

    String-valued because MLflow params are strings; ``agent_representative`` is
    ``"false"`` so dashboards can filter representative vs. non-representative
    runs without inferring it from the provider.
    """
    return {
        "execution_path": EXECUTION_PATH_ADDON_DIRECT,
        "agent_representative": "false",
    }
