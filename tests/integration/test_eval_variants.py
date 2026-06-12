#!/usr/bin/env python3
"""Tool-description A/B variant tests (issue #151).

Variants monkey-patch the descriptions the agent sees so we can A/B which
description style yields better tool selection. ``baseline`` is the control.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.variants import VARIANTS, apply_variant  # noqa: E402


def _tools() -> list[dict[str, object]]:
    return [
        {
            "name": "create_node",
            "description": "Add a new node to the scene. Use for building hierarchy.",
            "parameters": {"parent_path": {"type": "string"}, "name": {"type": "string"}},
        },
        {"name": "done", "description": "Signal that the task is complete. Call LAST."},
    ]


def test_at_least_three_variants_plus_baseline() -> None:
    assert "baseline" in VARIANTS
    assert len([v for v in VARIANTS if v != "baseline"]) >= 3


def test_baseline_is_identity() -> None:
    tools = _tools()
    out = apply_variant(tools, "baseline")
    assert [t["description"] for t in out] == [t["description"] for t in tools]


def test_variants_preserve_tool_names_and_count() -> None:
    tools = _tools()
    for variant in VARIANTS:
        out = apply_variant(tools, variant)
        assert [t["name"] for t in out] == [t["name"] for t in tools]


def test_concise_caps_description_length() -> None:
    out = apply_variant(_tools(), "concise")
    assert all(len(t["description"]) <= 80 for t in out)


def test_agent_opt_flags_when_to_use() -> None:
    out = apply_variant(_tools(), "agent_opt")
    assert all(t["description"].startswith("WHEN TO USE") for t in out)


def test_structured_surfaces_params() -> None:
    out = apply_variant(_tools(), "structured")
    create = next(t for t in out if t["name"] == "create_node")
    assert "parent_path" in create["description"]


def test_unknown_variant_raises() -> None:
    try:
        apply_variant(_tools(), "nope")
    except ValueError as e:
        assert "nope" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown variant")
