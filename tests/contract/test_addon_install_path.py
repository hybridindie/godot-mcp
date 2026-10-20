"""Contract: addon files resolve siblings relative to themselves (#742).

Consumers install the addon at arbitrary ``res://`` paths — e.g. a project that
keeps every editor addon under ``godot/`` installs it at
``res://godot/addons/godot_mcp/``. Any hardcoded ``res://addons/godot_mcp/``
path breaks there: the addon-version handshake reads ``""`` (the runtime
logger is now compiled from source, so it has no file path at all).

Sibling resources must be resolved from the calling script's own
``resource_path`` base dir.
"""

from __future__ import annotations

from pathlib import Path

_ADDON = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"


def test_no_addon_source_hardcodes_the_default_install_prefix() -> None:
    offenders = sorted(
        str(path.relative_to(_ADDON))
        for path in _ADDON.rglob("*.gd")
        if "res://addons/godot_mcp" in path.read_text(encoding="utf-8")
    )
    assert not offenders, (
        "hardcoded res://addons/godot_mcp path breaks non-default installs "
        f"(#742): {offenders}"
    )


def test_router_and_bridge_resolve_plugin_cfg_relative_to_themselves() -> None:
    for name in ("command_router.gd", "mcp_bridge.gd"):
        src = (_ADDON / name).read_text(encoding="utf-8")
        assert "get_script().resource_path.get_base_dir()" in src, (
            f"{name} must resolve plugin.cfg relative to its own script (#742)"
        )
