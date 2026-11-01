"""Contract: every registered tool has a row in ``docs/tool-contracts.md`` (#793).

The contract file is the per-tool source of truth, but nothing tied it to the
registry — three tools were prose-only, and one table block had lost its header
row (its rows carried a leading space, so Markdown stopped rendering it as a
table). These tests pin rows to the live surface and keep them uniform.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from pathlib import Path

from mcp_server.server import create_server
from mcp_server.transforms import _original_handler_name, godot_tool_name
from tests.helpers import list_all_tools

_CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "tool-contracts.md"
_ROW = re.compile(r"^\| `(godot_[a-z0-9_]+)` \|", re.MULTILINE)
_INDENTED_ROW = re.compile(r"^\s+\| `godot_[a-z0-9_]+` \|", re.MULTILINE)


def _live_tools() -> set[str]:
    server = create_server()
    tools = asyncio.run(list_all_tools(server))
    return {godot_tool_name(_original_handler_name(t), t.tags) for t in tools}


def test_every_registered_tool_has_a_contract_row() -> None:
    text = _CONTRACTS.read_text(encoding="utf-8")
    documented = set(_ROW.findall(text))
    live = _live_tools()

    missing = sorted(live - documented)
    phantom = sorted(documented - live)
    assert not missing, f"tools with no row in docs/tool-contracts.md: {missing}"
    assert not phantom, f"rows for unregistered tools: {phantom}"


def test_contract_rows_start_at_column_zero() -> None:
    """A leading space on a table row can silently drop it from the table."""
    text = _CONTRACTS.read_text(encoding="utf-8")
    indented = [match.group(0).strip() for match in _INDENTED_ROW.finditer(text)]
    assert not indented, f"table rows must start at column 0: {indented}"


def test_no_tool_has_more_than_one_contract_row() -> None:
    """One row per tool: a duplicated row hides registry drift and splits the contract."""
    text = _CONTRACTS.read_text(encoding="utf-8")
    counts = Counter(_ROW.findall(text))
    duplicated = sorted(tool for tool, count in counts.items() if count > 1)
    assert not duplicated, f"tools with more than one row in docs/tool-contracts.md: {duplicated}"
