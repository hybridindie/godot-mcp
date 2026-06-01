"""Smoke checks for the MCP server scaffold (issue #1).

These pin the package contract the rest of the build depends on: the package
imports cleanly with no import-time side effects, exposes a CalVer ``__version__``
consistent with packaging, and the planned subpackages exist.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CALVER = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:-\d+)?$")


def test_package_imports() -> None:
    import mcp_server

    assert mcp_server is not None


def test_version_is_calver() -> None:
    import mcp_server

    assert CALVER.match(mcp_server.__version__), (
        f"__version__ {mcp_server.__version__!r} is not CalVer YYYY.MM.DD[-N]"
    )


def test_version_matches_pyproject() -> None:
    import mcp_server

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert mcp_server.__version__ == pyproject["project"]["version"]


@pytest.mark.parametrize(
    "module",
    ["mcp_server.tools", "mcp_server.resources", "mcp_server.prompts", "mcp_server.models"],
)
def test_subpackages_import(module: str) -> None:
    assert importlib.import_module(module) is not None


def test_main_entrypoint_is_callable_without_import_side_effects() -> None:
    # Importing main must not connect sockets or run the server (async-patterns.md).
    main_mod = importlib.import_module("mcp_server.main")
    assert callable(main_mod.main)


def test_create_server_builds_without_io() -> None:
    # Building the server must not perform I/O or block (it runs in-process here).
    from mcp_server.server import create_server

    server = create_server()
    assert server is not None
