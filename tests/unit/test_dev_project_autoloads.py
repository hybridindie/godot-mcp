"""Guard: the dev project must not commit the runtime-probe autoload (issue #675).

The runtime e2e suites register the `MCPRuntimeProbe` autoload at test time and
restore `project.godot` from a snapshot afterwards, so it is expected to be
**absent** in the repo. A live bridge call that registered it once leaked the
autoload into a commit (#671); this pins it clean.
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_GODOT = Path(__file__).resolve().parents[2] / "godot" / "project.godot"


def test_runtime_probe_autoload_is_not_committed() -> None:
    text = _PROJECT_GODOT.read_text(encoding="utf-8")
    assert "GodotMcpProbe" not in text, (
        "the runtime-probe autoload must not be committed to godot/project.godot "
        "(the e2e registers/restores it at test time, #675)"
    )
