"""Contract: did-you-mean uses Godot 4.8's FuzzySearch when available (#603).

The engine matcher is 4.8+, and a static reference would break the 4.4 floor.
The addon resolves it through ClassDB, keeps the compact fallback for 4.4–4.7,
and the server documents why it stays on its local matcher.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ADDON = _ROOT / "godot" / "addons" / "godot_mcp"


def test_addon_prefers_fuzzy_search_but_keeps_the_floor_fallback() -> None:
    src = (_ADDON / "handlers" / "class_info.gd").read_text(encoding="utf-8")
    assert 'ClassDB.class_exists("FuzzySearch")' in src
    assert 'ClassDB.instantiate("FuzzySearch")' in src
    assert '"search_all"' in src
    assert '"filter_low_scores"' in src
    # The fallback must remain for 4.4–4.7.
    assert "func _closest(" in src
    assert "scored.sort_custom" in src


def test_server_keeps_local_matching_and_documents_the_choice() -> None:
    src = (_ROOT / "mcp_server" / "suggestions.py").read_text(encoding="utf-8")
    assert "import difflib" in src
    assert "FuzzySearch" in src and "no engine access" in src
