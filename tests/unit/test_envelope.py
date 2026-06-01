"""Unit tests for the JSON envelope models (issue #3)."""

from __future__ import annotations

import json

from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope


def test_command_envelope_wire_shape() -> None:
    cmd = CommandEnvelope(id="1", command="ping", params={"x": 1})
    data = json.loads(cmd.model_dump_json())
    assert data == {"id": "1", "command": "ping", "params": {"x": 1}}


def test_command_params_default_empty() -> None:
    cmd = CommandEnvelope(id="1", command="ping")
    assert cmd.params == {}


def test_response_success_factory() -> None:
    resp = ResponseEnvelope.success("1", {"pong": True})
    assert resp.ok is True
    assert resp.result == {"pong": True}
    assert resp.error is None
    # Success envelope serializes without null error/hint noise.
    assert json.loads(resp.model_dump_json()) == {"id": "1", "ok": True, "result": {"pong": True}}


def test_response_failure_factory() -> None:
    resp = ResponseEnvelope.failure("1", "RESOURCE_NOT_FOUND", "No node at 'X'.")
    assert resp.ok is False
    assert resp.error == "RESOURCE_NOT_FOUND"
    assert resp.hint == "No node at 'X'."
    assert resp.result is None


def test_response_precondition_failure_carries_required() -> None:
    resp = ResponseEnvelope.failure(
        "1", "PRECONDITION_FAILED", "Open a scene first.", required="active_scene"
    )
    data = json.loads(resp.model_dump_json())
    assert data["required"] == "active_scene"


def test_response_roundtrips_from_addon_json() -> None:
    raw = '{"id": "7", "ok": true, "result": {"pong": true}}'
    resp = ResponseEnvelope.model_validate_json(raw)
    assert resp.id == "7"
    assert resp.ok is True
    assert resp.result == {"pong": True}
