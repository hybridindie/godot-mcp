"""Contract: the runtime probe stays parseable on the Godot 4.4 floor (#648, #738).

`Logger` and `OS.add_logger` are Godot 4.5+ APIs. A Logger subclass in a `.gd`
file is parsed by the editor even without a `class_name`, so a real 4.4 editor
load fails (issue #738 — the first 4.4 CI run caught exactly this). The probe
therefore compiles the subclass from an embedded string, gated on the 4.5+ API.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
_MARKER = 'const _LOGGER_SOURCE := """'


def _split_logger_source(src: str) -> tuple[str, str]:
    """Return (embedded Logger source, all probe source outside that string)."""
    start = src.index(_MARKER)
    body_start = start + len(_MARKER)
    body_end = src.index('"""', body_start)
    return src[body_start:body_end], src[:start] + src[body_end + 3 :]


def test_probe_never_references_the_45_logger_api_outside_the_embedded_source() -> None:
    src = (_ADDON / "mcp_runtime_probe.gd").read_text(encoding="utf-8")
    _logger_source, outside = _split_logger_source(src)
    for forbidden in (
        "extends Logger",
        "var _output_logger: Logger",
        "OS.add_logger(",
        "OS.remove_logger(",
    ):
        assert forbidden not in outside, f"probe references 4.5 API '{forbidden}' (#648)"
    # The guarded path uses method-existence + a dynamic call (no compile-time ref).
    assert 'OS.has_method("add_logger")' in outside
    assert 'OS.has_method("remove_logger")' in outside
    assert "OS.call(" in outside


def test_the_logger_is_compiled_lazily_not_shipped_as_a_gd_script() -> None:
    # A .gd file would be parsed by the 4.4 editor at project load.
    assert not (_ADDON / "mcp_output_logger.gd").exists(), (
        "the Logger subclass must not exist as a .gd file — the 4.4 editor parses "
        "every script and fails on `extends Logger` (#738)"
    )
    src = (_ADDON / "mcp_runtime_probe.gd").read_text(encoding="utf-8")
    logger_source, outside = _split_logger_source(src)
    assert "extends Logger" in logger_source
    assert "class_name " not in logger_source
    assert "GDScript.new()" in outside and ".source_code" in outside
    assert ".reload()" in outside
