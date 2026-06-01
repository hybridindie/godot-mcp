"""Smoke checks for the Godot addon scaffold (issue #1).

The addon side cannot be unit-tested by running Godot here, so these pin the
parts that are statically checkable: the ``plugin.cfg`` manifest is well-formed
and points at a real ``@tool extends EditorPlugin`` script, the project enables
the plugin, and the addon version stays in lockstep with the Python package
(both CalVer). Loading the plugin in the Godot 4.4 editor is the addon-side
preflight (see .claude/rules/workflow.md).
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

import mcp_server

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
PLUGIN_CFG = ADDON_DIR / "plugin.cfg"
PROJECT_GODOT = REPO_ROOT / "godot" / "project.godot"
CALVER = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:-\d+)?$")


@pytest.fixture
def plugin_cfg() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(PLUGIN_CFG)
    return parser


def test_plugin_cfg_exists() -> None:
    assert PLUGIN_CFG.is_file(), f"missing addon manifest at {PLUGIN_CFG}"


@pytest.mark.parametrize("key", ["name", "description", "author", "version", "script"])
def test_plugin_cfg_has_required_keys(plugin_cfg: configparser.ConfigParser, key: str) -> None:
    assert plugin_cfg.has_option("plugin", key), f"plugin.cfg [plugin] missing {key!r}"
    assert plugin_cfg.get("plugin", key).strip('"'), f"plugin.cfg {key!r} is empty"


def test_plugin_script_exists_and_is_editor_plugin(
    plugin_cfg: configparser.ConfigParser,
) -> None:
    script_name = plugin_cfg.get("plugin", "script").strip('"')
    script_path = ADDON_DIR / script_name
    assert script_path.is_file(), f"plugin script {script_name!r} not found"
    source = script_path.read_text()
    assert "@tool" in source, "addon script must carry @tool"
    assert "extends EditorPlugin" in source, "addon entry must extend EditorPlugin"


def test_addon_version_matches_package(plugin_cfg: configparser.ConfigParser) -> None:
    version = plugin_cfg.get("plugin", "version").strip('"')
    assert CALVER.match(version), f"addon version {version!r} is not CalVer"
    assert version == mcp_server.__version__, "addon and server versions drifted"


def test_project_godot_enables_plugin() -> None:
    assert PROJECT_GODOT.is_file(), "godot/project.godot must exist so the addon is loadable"
    text = PROJECT_GODOT.read_text()
    assert "res://addons/godot_mcp/plugin.cfg" in text, "project must enable the godot_mcp plugin"
