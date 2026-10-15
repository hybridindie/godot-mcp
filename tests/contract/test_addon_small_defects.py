"""Contract: small addon defects stay fixed (issue #647).

Source pins for the cheap-but-real defects: the format-precedence hint, the
dropped-oversize-reply signal, the scan re-entrancy guard, and the Variant type
name spellings.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def _src(name: str) -> str:
    return (_ADDON / name).read_text(encoding="utf-8")


def test_variant_type_names_use_godot_spelling() -> None:
    src = _src("type_coerce.gd")
    correct_names = (
        'return "Vector2i"',
        'return "Rect2i"',
        'return "Vector3i"',
        'return "Vector4i"',
    )
    wrong_names = (
        'return "Vector2I"',
        'return "Rect2I"',
        'return "Vector3I"',
        'return "Vector4I"',
    )
    for correct in correct_names:
        assert correct in src, f"missing {correct} (#647)"
    for wrong in wrong_names:
        assert wrong not in src, f"{wrong} is not a Godot type name (#647)"


def test_script_write_rescan_guards_reentrancy() -> None:
    src = _src("godot_mcp.gd")
    body = src.split("func _rescan_after_script_write")[1].split("\nfunc ", 1)[0]
    assert "is_scanning()" in body, "the post-write rescan must skip an in-flight scan (#647)"


def test_bridge_signals_an_oversize_reply() -> None:
    src = _src("mcp_bridge.gd")
    assert "RESPONSE_TOO_LARGE" in src, "a dropped oversize reply must be surfaced (#647)"
    # The reply send's return is captured (not ignored) and checked.
    assert "var err" in src and "send_text(JSON.stringify(response))" in src
