"""Direct unit tests for the bridge transport helpers (#829).

These were only exercised indirectly through the bridge contract suite before
the #801/#829 extraction.
"""

from __future__ import annotations

import json

import pytest

from mcp_server.bridge_helpers import DEFAULT_BRIDGE_PORT, bind_target, supplied_token


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("ws://127.0.0.1:9080", ("127.0.0.1", 9080)),
        ("ws://localhost:4000", ("127.0.0.1", 4000)),  # IPv4 normalisation
        ("ws://example.test:1234", ("example.test", 1234)),
        ("ws://127.0.0.1", ("127.0.0.1", DEFAULT_BRIDGE_PORT)),
        ("not-a-url", ("127.0.0.1", DEFAULT_BRIDGE_PORT)),
    ],
)
def test_bind_target(url: str, expected: tuple[str, int]) -> None:
    assert bind_target(url) == expected


def _auth(token: str) -> str:
    return json.dumps({"id": "auth", "command": "cmd_auth", "params": {"token": token}})


def test_supplied_token_reads_a_valid_auth_envelope() -> None:
    assert supplied_token(_auth("s3cret")) == ("s3cret", True)
    assert supplied_token(_auth("").encode()) == ("", True)  # bytes frame, empty token


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps(["cmd_auth"]),
        json.dumps({"id": "x", "command": "cmd_ping", "params": {"token": "t"}}),
        json.dumps({"id": "x", "command": "cmd_auth", "params": "not-a-dict"}),
        json.dumps({"id": "x", "command": "cmd_auth"}),
    ],
)
def test_supplied_token_ignores_non_auth_shapes(raw: str) -> None:
    # A control message racing ahead of the auth envelope must be skipped, never
    # treated as an empty-token auth attempt (which would falsely refuse it).
    assert supplied_token(raw) == ("", False)
