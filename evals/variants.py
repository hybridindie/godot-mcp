#!/usr/bin/env python3
"""Tool-description A/B variants for the LLM eval (issue #151).

The 2026-06-10 gap analysis flagged that we don't know which tool-description
style works best for real LLMs. These variants monkey-patch the descriptions
the agent sees (the get_available_tools() list) at runtime so the eval can A/B
them under the same git SHA. ``baseline`` is the control (unchanged).

Transforms are generic (driven by each tool's own description/parameters), so
they apply to the whole catalog without per-tool maintenance.

Usage:
    python -m evals.variants            # list variants and validate they run
    python -m evals.llm_eval_v2 --variant concise
"""

from __future__ import annotations

from collections.abc import Callable


def _first_sentence(desc: str) -> str:
    if not desc:
        return desc
    head = desc.split(". ")[0].rstrip(".")
    return f"{head}."


def _concise(tool: dict) -> dict:
    """One-line description: the first sentence, capped at 80 chars."""
    short = _first_sentence(str(tool.get("description", "")))[:80]
    return {**tool, "description": short}


def _structured(tool: dict) -> dict:
    """JSON-schema-style: description plus an explicit ``params:`` block."""
    desc = str(tool.get("description", ""))
    params = tool.get("parameters", {})
    if params:
        param_str = ", ".join(
            f"{name}: {spec.get('type', 'any')}" for name, spec in params.items()
        )
        desc = f"{desc} | params: {param_str}"
    return {**tool, "description": desc}


def _agent_opt(tool: dict) -> dict:
    """Prefix a 'WHEN TO USE' cue derived from the first sentence."""
    desc = str(tool.get("description", ""))
    return {**tool, "description": f"WHEN TO USE: {_first_sentence(desc)} {desc}".strip()}


# Per-tool transforms. ``baseline`` is the identity control.
VARIANTS: dict[str, Callable[[dict], dict]] = {
    "baseline": lambda tool: dict(tool),
    "concise": _concise,
    "structured": _structured,
    "agent_opt": _agent_opt,
}


def apply_variant(tools: list[dict], variant: str) -> list[dict]:
    """Return ``tools`` with the named variant's transform applied to each.

    Raises ``ValueError`` for an unknown variant.
    """
    transform = VARIANTS.get(variant)
    if transform is None:
        raise ValueError(
            f"Unknown variant '{variant}'. Choices: {', '.join(VARIANTS)}"
        )
    return [transform(t) for t in tools]


def _main() -> None:
    # Validation entrypoint for CI: every variant must transform the live tool
    # catalog without error and preserve tool names.
    from evals.llm_eval_v2 import get_available_tools

    tools = get_available_tools()
    names = [t["name"] for t in tools]
    for variant in VARIANTS:
        out = apply_variant(tools, variant)
        assert [t["name"] for t in out] == names, f"{variant} dropped/renamed tools"
        print(f"✓ {variant}: {len(out)} tools")
    print(f"\n{len(VARIANTS)} variants OK over {len(tools)} tools.")


if __name__ == "__main__":
    _main()
