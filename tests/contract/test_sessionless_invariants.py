"""Sessionless-surface guard (issue #386).

The MCP spec's 2026-07-28 revision removes sessions and the ``initialize``
handshake. godot-mcp committed to the sessionless shape in #364/#370: toolset
gating is a single server-global set (no ``context.session_id`` keying, no
``Middleware.on_initialize``), and the approval guard is durable via
``request_state`` round-trips (no server-side per-session state).

The behavior is pinned by ``test_toolset_global_state.py`` and
``test_approval_guard.py``. This guard pins the **source shape**: no module
under ``mcp_server/`` may key server state on session identity again — a drift
back toward ``session_id`` / ``ctx.session`` / per-session middleware hooks
would silently break on the sessionless protocol (a fresh ``session_id`` per
call makes per-session state a no-op), the exact failure mode #386 exists to
avoid discovering late.

The scan is AST-based (not a text grep) so docstrings/comments mentioning
"sessions" — which are legion and correct — don't trip it. Only *code* that
reads a ``.session_id`` / ``.session`` attribute, names a binding
``session_id``, or defines an ``on_initialize`` / ``on_new_session`` /
``on_session_end`` method counts as a violation.
"""

from __future__ import annotations

import ast
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[2] / "mcp_server"

# Middleware hooks that assume session lifecycle (2025-era semantics).
_SESSION_HOOKS = {"on_initialize", "on_new_session", "on_session_end"}

# Attribute names that read session identity off a context/ctx object.
_SESSION_ATTRS = {"session_id", "session"}

VIOLATION_READS_SESSION = "ctx_id = ctx.session_id"
VIOLATION_HOOK = "class M:\n    def on_initialize(self, ctx):\n        pass\n"


def _violations(tree: ast.Module, rel: Path) -> list[str]:
    """Return human-readable session-keying violations in one module."""
    found: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr in _SESSION_ATTRS:
                found.append(f"{rel}: reads .{node.attr} (line {node.lineno})")
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "session_id":
                found.append(f"{rel}: names `session_id` (line {node.lineno})")
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node.name in _SESSION_HOOKS:
                found.append(f"{rel}: defines `{node.name}` (line {node.lineno})")
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node.name in _SESSION_HOOKS:
                found.append(f"{rel}: defines `{node.name}` (line {node.lineno})")
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found


def _all_server_modules() -> list[tuple[Path, ast.Module]]:
    modules: list[tuple[Path, ast.Module]] = []
    for py in sorted(MCP_SERVER_DIR.rglob("*.py")):
        modules.append((py, ast.parse(py.read_text(encoding="utf-8"), filename=str(py))))
    return modules


def test_no_server_code_keys_state_on_session_identity() -> None:
    """No ``mcp_server/`` module reads session identity or defines session hooks."""
    assert MCP_SERVER_DIR.is_dir()
    violations: list[str] = []
    for py, tree in _all_server_modules():
        rel = py.relative_to(MCP_SERVER_DIR)
        violations.extend(_violations(tree, rel))
    assert not violations, "\n".join(sorted(violations))


def test_guard_trips_on_a_deliberate_violation() -> None:
    """The guard is not vacuous: injected session keying is caught.

    This is the red-first proof for the guard itself — the same detection the
    main test runs over real modules, exercised against code that actually
    reads ``ctx.session_id`` and defines an ``on_initialize`` hook.
    """
    v1 = _violations(ast.parse(VIOLATION_READS_SESSION), Path("fake.py"))
    v2 = _violations(ast.parse(VIOLATION_HOOK), Path("fake2.py"))
    assert any(".session_id" in v for v in v1)
    assert any("on_initialize" in v for v in v2)
