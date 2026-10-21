"""Unit: the Godot 4.8-beta1 gate is anchored to beta1, not a substring (#739).

The gate chooses the known-bad MeshLibrary shape on beta1. A substring match
would also fire on ``4.8.beta10`` (or a future stable string that contains
``4.8.beta1``), silently weakening the assertion.
"""

from __future__ import annotations

import pytest

from tests.integration import _godot


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("4.8.beta1.official.4d10419ca", True),
        ("4.8-beta1", True),
        ("4.8.beta10.official.abc", False),
        ("4.8.stable.official.abc", False),
        ("4.7.2.stable.fedora.ed1daf0bf", False),
        ("", False),
    ],
)
def test_48_beta1_gate(monkeypatch: pytest.MonkeyPatch, version: str, expected: bool) -> None:
    monkeypatch.setattr(_godot, "godot_version", lambda: version)
    assert _godot.is_godot_48_beta1() is expected
