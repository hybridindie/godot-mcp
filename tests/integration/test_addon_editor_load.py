"""Integration test: the addon enables in the editor without errors (issue #2).

Loads the project in the headless Godot *editor*, which enables the plugin listed
in ``project.godot`` — running ``godot_mcp.gd``'s ``_enter_tree``, adding the dock,
and querying ``EditorInterface``. A parse error, a bad API call, or a failed dock
add would surface as ``SCRIPT ERROR`` and/or a non-zero exit. This is the
automated form of the "enables/disables cleanly without crashing the editor"
acceptance criterion.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_editor_loads_addon_without_errors() -> None:
    # --editor --quit imports the project, enables plugins, then exits.
    result = run_godot(["--editor", "--quit"])
    output = result.stdout + result.stderr

    assert result.returncode == 0, f"editor exited {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output, f"GDScript error during editor load:\n{output}"
    # Catch a plugin that fails to instantiate/enable even if exit code is lenient.
    for marker in ("Unable to load addon script", "Failed to instantiate an autoload"):
        assert marker not in output, f"addon failed to enable ({marker!r}):\n{output}"
