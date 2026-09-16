"""Integration test: the addon leaks no objects or resources when the editor exits.

``MCPCommandRouter`` holds its 31 handler instances as members and every handler keeps
a ``_router`` back-reference, so the router and its handlers form a RefCounted cycle.
RefCounted cycles never reach a zero reference count (see the Godot ``RefCounted``
class reference), which left the router, the handler instances and their scripts alive
at process exit: a headless editor run ended with ``ObjectDB instances were leaked at
exit`` and ``resources still in use at exit`` even though all of it belonged to the
addon. ``MCPBridge.dispose()`` now breaks the cycle on the plugin's exit path.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# Printed by core/object/object.cpp and core/io/resource.cpp at process exit when
# objects / resources are still alive.
_LEAK_MARKERS = (
    "ObjectDB instances were leaked",
    "resources still in use at exit",
)


def test_editor_exit_reports_no_leaks() -> None:
    # --editor --quit enables the plugin, builds the router + handler instances, exits.
    result = run_godot(["--editor", "--quit"])
    output = result.stdout + result.stderr

    assert result.returncode == 0, f"editor exited {result.returncode}:\n{output}"
    for marker in _LEAK_MARKERS:
        assert marker not in output, f"leak at editor exit ({marker!r}):\n{output}"
