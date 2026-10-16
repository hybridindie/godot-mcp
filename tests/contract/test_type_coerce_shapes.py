"""Contract test pinning the extended JSON shapes (issue #641).

The headless smoke (`godot/tests/type_coerce_smoke.gd`, run in CI via
`tests/integration/test_addon_read_smokes.py`) is the behavioural pin; this
source-level test guards that the extended Variant types and the non-finite
float sentinels stay defined, and that the runtime probe reuses the one
implementation (no second `_json_safe` copy).
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"

_EXTENDED_TYPES = [
    "TYPE_TRANSFORM2D",
    "TYPE_TRANSFORM3D",
    "TYPE_BASIS",
    "TYPE_QUATERNION",
    "TYPE_AABB",
    "TYPE_PLANE",
    "TYPE_PROJECTION",
    "TYPE_PACKED_BYTE_ARRAY",
    "TYPE_PACKED_VECTOR2_ARRAY",
    "TYPE_PACKED_VECTOR3_ARRAY",
    "TYPE_PACKED_COLOR_ARRAY",
]


def test_type_coerce_covers_extended_variant_types() -> None:
    src = (_ADDON / "type_coerce.gd").read_text(encoding="utf-8")
    missing = [t for t in _EXTENDED_TYPES if t not in src]
    assert not missing, f"type_coerce.gd must handle: {missing} (#641)"


def test_non_finite_floats_have_explicit_sentinels() -> None:
    src = (_ADDON / "type_coerce.gd").read_text(encoding="utf-8")
    for sentinel in ("__nan__", "__inf__", "__-inf__"):
        assert sentinel in src, f"missing non-finite sentinel {sentinel} (#641)"


def test_probe_reuses_type_coerce_single_implementation() -> None:
    src = (_ADDON / "mcp_runtime_probe.gd").read_text(encoding="utf-8")
    assert 'preload("type_coerce.gd")' in src, "the probe must reuse type_coerce (#641)"
    assert "_json_safe" not in src, "the probe's duplicate _json_safe must be gone (#641)"
