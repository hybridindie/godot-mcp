"""Contract tests: godot_mcp:ui_elements replies gated on request_id (#577).

The #575 Qodo review flagged the stale-reply hole in the one-shot read cache
and noted "the find_ui_elements pattern (which this mirrors) should have the
same issue" — the pre-existing godot_mcp:ui_elements capture stored every
reply without validating its request_id against the pending scan, so a
delayed reply to an OLDER request could be served to a new poll with
different filters (wrong rects to click).

Contract (mirrors the #575 read_property fix, same two gates):
- the debugger's godot_mcp:ui_elements capture stores a reply only when its
  request_id matches the pending scan (_ui_pending);
- the handler re-verifies the id before serving the cache (already present —
  pinned here so both halves hold).
"""

from __future__ import annotations

from pathlib import Path

from tests.integration.test_addon_read_smokes import SMOKES

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"


def test_ui_elements_capture_gates_on_pending_request_id() -> None:
    """The capture must drop replies whose request_id isn't the pending scan."""
    src = (ADDON_DIR / "mcp_debugger.gd").read_text()
    capture = src.split('"godot_mcp:ui_elements":', 1)[1].split("return true", 1)[0]
    assert "_ui_pending" in capture, (
        "godot_mcp:ui_elements capture must gate the cache on the pending "
        "request_id (a delayed reply to an older scan must not be served to a "
        "new poll — #577, mirroring the #575 read_property fix)"
    )
    assert "request_id" in capture


def test_ui_elements_handler_reverifies_request_id() -> None:
    """The handler's fast-path id match stays (belt-and-braces, unchanged)."""
    handler = (ADDON_DIR / "handlers" / "runtime_inspect.gd").read_text().split(
        "func _cmd_find_ui_elements", 1
    )[1].split("func ", 1)[0]
    assert 'get("request_id") == request_id' in handler


def test_ui_elements_gate_smoke_is_wired_into_pytest() -> None:
    """The behavioral smoke runs in CI on the self-hosted e2e runner."""
    assert ("ui_elements_gate_smoke.gd", "UI_ELEMENTS_GATE_TEST_OK") in SMOKES