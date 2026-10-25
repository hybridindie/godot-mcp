"""Contract: ``docs/site/reference-toolsets.md`` is generated, not hand-edited (#828).

The site catalog duplicated all 201 rows from ``docs/tool-contracts.md`` by hand
and drifted (the ``project`` count was stale after the scan tool landed). The
generator rewrites only the counts/tables; these tests keep it honest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_toolset_catalog.py"
DOC = ROOT / "docs" / "site" / "reference-toolsets.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_catalog_is_up_to_date() -> None:
    result = _run("--check")
    assert result.returncode == 0, f"catalog is stale:\n{result.stderr}"
    assert "up to date" in result.stdout


def test_check_detects_a_stale_count(tmp_path: Path) -> None:
    copy = tmp_path / "catalog.md"
    copy.write_text(
        DOC.read_text(encoding="utf-8").replace("10 tools.", "11 tools.", 1),
        encoding="utf-8",
    )
    result = _run("--check", "--file", str(copy))
    assert result.returncode == 1
    assert "stale" in result.stderr
    assert "11 tools." in result.stderr  # shows the offending line in the diff


def test_check_detects_a_missing_row(tmp_path: Path) -> None:
    copy = tmp_path / "catalog.md"
    text = DOC.read_text(encoding="utf-8")
    row = next(
        line for line in text.splitlines() if line.startswith("| `godot_analysis_")
    )
    copy.write_text(text.replace(row + "\n", "", 1), encoding="utf-8")
    result = _run("--check", "--file", str(copy))
    assert result.returncode == 1, "a removed tool row must be caught"
    assert "stale" in result.stderr
