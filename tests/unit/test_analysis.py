"""Unit tests for static analysis (issue #49) over a synthetic project tree."""

from __future__ import annotations

from pathlib import Path

from mcp_server import analysis


def _make_project(root: Path) -> None:
    (root / "project.godot").write_text(
        'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n'
        '[autoload]\nGame="*res://game.gd"\n',
        encoding="utf-8",
    )
    # main.tscn references an icon, the game script, and declares a connection
    (root / "main.tscn").write_text(
        "[gd_scene load_steps=3 format=3]\n"
        '[ext_resource type="Texture2D" path="res://used.png" id="1"]\n'
        '[ext_resource type="Script" path="res://game.gd" id="2"]\n'
        '[node name="Main" type="Node2D"]\n'
        '[node name="Button" type="Button" parent="."]\n'
        '[connection signal="pressed" from="Button" to="." method="_on_pressed"]\n',
        encoding="utf-8",
    )
    (root / "used.png").write_bytes(b"\x89PNG\r\n")  # content irrelevant
    (root / "unused.png").write_bytes(b"\x89PNG\r\n")
    (root / "game.gd").write_text(
        'extends Node\nconst A = preload("res://a.gd")\n', encoding="utf-8"
    )
    # a.gd <-> b.gd form a cycle
    (root / "a.gd").write_text('extends Node\nconst B = preload("res://b.gd")\n', encoding="utf-8")
    (root / "b.gd").write_text('extends Node\nconst A = preload("res://a.gd")\n', encoding="utf-8")
    (root / "lonely.gd").write_text("extends Node\n", encoding="utf-8")


def test_find_unused_resources(tmp_path: Path) -> None:
    _make_project(tmp_path)
    index = analysis.scan(tmp_path)
    result = analysis.find_unused_resources(index)
    assert "res://unused.png" in result["unused"]
    assert "res://used.png" not in result["unused"]
    assert "res://main.tscn" not in result["unused"]  # entry point (main scene)
    assert "res://game.gd" not in result["unused"]  # entry point (autoload)


def test_analyze_signal_flow(tmp_path: Path) -> None:
    _make_project(tmp_path)
    index = analysis.scan(tmp_path)
    flow = analysis.analyze_signal_flow(index)
    assert flow["count"] == 1
    conn = flow["connections"][0]
    assert conn["scene"] == "res://main.tscn"
    assert conn["signal"] == "pressed" and conn["method"] == "_on_pressed"
    # scoping to a non-matching scene yields nothing
    assert analysis.analyze_signal_flow(index, "res://other.tscn")["count"] == 0


def test_detect_circular_dependencies(tmp_path: Path) -> None:
    _make_project(tmp_path)
    index = analysis.scan(tmp_path)
    result = analysis.detect_circular_dependencies(index)
    assert result["count"] == 1
    cycle_list = result["cycles"][0]
    assert len(cycle_list) == len(set(cycle_list))  # no duplicated closing node
    assert set(cycle_list) == {"res://a.gd", "res://b.gd"}


def test_plugin_cfg_script_is_an_entry_point(tmp_path: Path) -> None:
    addon = tmp_path / "addons" / "demo"
    addon.mkdir(parents=True)
    # relative script= (the common form) and an absolute one both resolve to res:// paths
    (addon / "plugin.cfg").write_text('[plugin]\nscript="demo.gd"\n', encoding="utf-8")
    (addon / "demo.gd").write_text("@tool\nextends EditorPlugin\n", encoding="utf-8")
    abs_addon = tmp_path / "addons" / "abs"
    abs_addon.mkdir(parents=True)
    (abs_addon / "plugin.cfg").write_text(
        '[plugin]\nscript="res://addons/abs/abs.gd"\n', encoding="utf-8"
    )
    (abs_addon / "abs.gd").write_text("@tool\nextends EditorPlugin\n", encoding="utf-8")
    index = analysis.scan(tmp_path)
    unused = analysis.find_unused_resources(index)["unused"]
    assert "res://addons/demo/demo.gd" not in unused
    assert "res://addons/abs/abs.gd" not in unused


def test_project_stats(tmp_path: Path) -> None:
    _make_project(tmp_path)
    index = analysis.scan(tmp_path)
    stats = analysis.project_stats(index)
    assert stats["scenes"] == 1
    assert stats["scripts"] == 4  # game, a, b, lonely
    assert stats["total_nodes"] == 2  # Main + Button
    assert stats["connections"] == 1
    assert stats["by_extension"][".png"] == 2
    assert stats["busiest_scenes"][0]["scene"] == "res://main.tscn"


def test_scan_skips_godot_cache(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / ".godot").mkdir()
    (tmp_path / ".godot" / "cached.png").write_bytes(b"x")
    index = analysis.scan(tmp_path)
    assert "res://.godot/cached.png" not in index.resources
