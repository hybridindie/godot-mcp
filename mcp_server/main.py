"""stdio entrypoint for the godot-mcp FastMCP server.

This is a scaffold placeholder (issue #1). The FastMCP server instance, the
``health_check`` tool, and the bridge wiring are bootstrapped in issue #4. Keeping
this thin avoids import-time side effects (no socket connect, no ``mcp.run()`` at
import — see .claude/rules/async-patterns.md).
"""

from __future__ import annotations

from mcp_server import __version__


def main() -> None:
    """Console-script entry point (``godot-mcp``).

    Replaced in issue #4 with the FastMCP stdio server. For now it only reports
    that the server is not yet bootstrapped so the entry point is wired and
    importable without performing any I/O at import time.
    """
    raise SystemExit(
        f"godot-mcp {__version__}: server entrypoint not yet bootstrapped (issue #4)."
    )


if __name__ == "__main__":
    main()
