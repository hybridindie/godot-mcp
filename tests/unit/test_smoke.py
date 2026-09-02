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
CALVER = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:[-.]?(?:\d+|(?:a|b|rc)\d+))?$")


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


def test_fastmcp_pinned_to_4_stable() -> None:
    # fastmcp is pinned to the 4.0 stable line (issue #403, closing the #311
    # promise "follow stable 4.x when it ships"). GA is built on MCP SDK v2 and
    # the 2026-07-28 sessionless protocol revision. The pin is exact — the
    # slim/tasks constraint block in [tool.uv] must move in lockstep, which the
    # upgrade updates alongside this test. 4.0.1 = GA + ClientGroup reentrancy.
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]
    fastmcp = next((d for d in dependencies if d.replace(" ", "").startswith("fastmcp")), None)
    assert fastmcp is not None, "fastmcp dependency missing from pyproject"
    spec = fastmcp.replace(" ", "")
    assert spec == "fastmcp[tasks]==4.0.1", (
        f"fastmcp must pin exactly fastmcp[tasks]==4.0.1, got {fastmcp!r}"
    )
    constraints = pyproject["tool"]["uv"]["constraint-dependencies"]
    assert "fastmcp-slim==4.0.1" in constraints, "slim must ride the same stable pin"
    assert "fastmcp-tasks==4.0.1" in constraints, "tasks must ride the same stable pin"


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
