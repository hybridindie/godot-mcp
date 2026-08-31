"""Guard the ``evals/`` surface after the harness move to godot-agents (issue #383).

godot-mcp is game-agnostic and consumer-independent, so the LLM eval
**harness** (agents, task suites, variant A/B machinery) is a consumer
concern — it now lives in ``godot_agent_harness`` inside godot-agents
(godot-agents#481). This module pins what must *stay* and what must be
*gone* in this repo:

- Stays: ``evals/instruction_staleness.py`` — server self-analysis of its
  own tool docs vs. bridge handlers (never references an agent).
- Gone: every harness module, the ``archive/`` / ``results/`` artifacts,
  the moved tests, and any ``import evals`` reference to a moved module.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"
TESTS_DIR = REPO_ROOT / "tests"

# Modules that moved to godot-agents (godot_agent_harness / its tests).
MOVED_MODULES = {
    "agent_suite_v2",
    "batch_perf_test",
    "cloud_client",
    "composition_test",
    "correction",
    "cross_model_compare",
    "history",
    "llm_eval_v2",
    "negative_test",
    "ollama_agent",
    "profiler",
    "transition_test",
    "variant_ab_test",
    "variants",
}
MOVED_TESTS = {
    "test_eval_corrections.py",
    "test_eval_history.py",
    "test_eval_milestones.py",
    "test_eval_representativeness.py",
    "test_eval_variants.py",
}

# evals/ keeps exactly these files (plus this guard's subject module).
EXPECTED_EVALS_FILES = {
    "instruction_staleness.py",
    "README.md",
}

# An ``import evals`` / ``from evals`` statement, capturing the module path.
EVALS_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+evals(?:\s+import\s+([\w. ,]+)|\.([\w.]+))",
    re.MULTILINE,
)


def _evals_files() -> set[str]:
    """Trackable files under evals/ (skip __pycache__ and dotfiles)."""
    if not EVALS_DIR.is_dir():
        return set()
    return {
        str(p.relative_to(EVALS_DIR))
        for p in EVALS_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")
    }


def test_evals_dir_holds_only_server_self_analysis() -> None:
    """evals/ contains exactly the staleness verifier + its README."""
    assert EVALS_DIR.is_dir(), "evals/ directory must exist for instruction_staleness"
    files = _evals_files()
    unexpected = sorted(files - EXPECTED_EVALS_FILES)
    assert not unexpected, (
        "Harness files remain in evals/ after the move to godot-agents "
        f"(issue #383): {unexpected}"
    )
    missing = sorted(EXPECTED_EVALS_FILES - files)
    assert not missing, f"Expected remnant files missing from evals/: {missing}"


def test_moved_eval_tests_are_gone() -> None:
    """Tests for moved harness modules were deleted, not left dangling."""
    leftovers = [
        name
        for name in MOVED_TESTS
        if list(TESTS_DIR.rglob(name))
    ]
    assert not leftovers, (
        "Tests for harness modules moved to godot-agents still exist here "
        f"(issue #383): {leftovers}"
    )


def test_no_imports_of_moved_eval_modules() -> None:
    """No godot-mcp file imports a harness module that moved to godot-agents."""
    offenders: list[str] = []
    scanned: list[Path] = [
        *REPO_ROOT.glob("*.py"),
        *(REPO_ROOT / "tests").rglob("*.py"),
        *(REPO_ROOT / "mcp_server").rglob("*.py"),
    ]
    for py in scanned:
        text = py.read_text(encoding="utf-8")
        for match in EVALS_IMPORT_RE.finditer(text):
            target = (match.group(1) or match.group(2) or "").split(".")[0].strip()
            if target in MOVED_MODULES:
                offenders.append(f"{py.relative_to(REPO_ROOT)}: evals.{target}")
    assert not offenders, (
        "Imports of harness modules that moved to godot-agents "
        f"(issue #383): {offenders}"
    )


def test_staleness_module_stays_self_contained() -> None:
    """The remnant static analyzer must not depend on any moved harness module."""
    text = (EVALS_DIR / "instruction_staleness.py").read_text(encoding="utf-8")
    deps = sorted(EVALS_IMPORT_RE.findall(text))
    assert not deps, f"instruction_staleness.py imports evals modules: {deps}"
    assert "from mcp_server.bridge import Bridge" in text