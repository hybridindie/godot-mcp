"""Contract: the runtime probe stays parseable on the Godot 4.4 floor (issue #648).

`Logger` and `OS.add_logger` are Godot 4.5+ APIs. The probe must not reference
them directly — that would be a parse error on 4.4, killing every runtime
feature. The logger lives in a separate, class_name-free script the probe
`load()`s only when the API exists.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def test_probe_never_references_the_45_logger_api_directly() -> None:
    src = (_ADDON / "mcp_runtime_probe.gd").read_text(encoding="utf-8")
    for forbidden in (
        "extends Logger",
        "var _output_logger: Logger",
        "OS.add_logger(",
        "OS.remove_logger(",
    ):
        assert forbidden not in src, f"probe references 4.5 API '{forbidden}' (#648)"
    # The guarded path uses method-existence + a dynamic call (no compile-time ref).
    assert 'OS.has_method("add_logger")' in src
    assert 'OS.has_method("remove_logger")' in src
    assert "OS.call(" in src


def test_output_logger_script_is_lazy_and_unregistered() -> None:
    src = (_ADDON / "mcp_output_logger.gd").read_text(encoding="utf-8")
    assert "extends Logger" in src  # the 4.5 type lives only here
    assert "class_name " not in src, (
        "a class_name declaration would force the editor to parse it on 4.4 (#648)"
    )
