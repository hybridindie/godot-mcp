"""Human-in-the-loop approval gate for destructive tools (issue #153).

The gate is opt-in: with no webhook configured it auto-approves (so evals and
headless runs are never blocked). When a webhook is set, destructive tools must
be approved; unreachable webhooks fail open or closed per config. The HTTP
poster is injected, so this is a pure unit test — no network.
"""

from __future__ import annotations

import json

import pytest
from mcp.types import ElicitRequestFormParams

from mcp_server.approval_middleware import APPROVE_KEY, _build_input_required
from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalRequest, ApprovalResponse
from mcp_server.safety import (
    ApprovalGate,
    ApprovalPoster,
    PreconditionError,
    parse_approval_response,
)

pytestmark = pytest.mark.asyncio


def _poster(
    response: ApprovalResponse | None = None, *, raises: Exception | None = None
) -> tuple[ApprovalPoster, list[ApprovalRequest]]:
    """Return a fake poster and the list it records each request into."""
    seen: list[ApprovalRequest] = []

    async def poster(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
        seen.append(request)
        if raises is not None:
            raise raises
        return response or ApprovalResponse(approved=True)

    return poster, seen


async def test_no_webhook_auto_approves() -> None:
    gate = ApprovalGate()  # webhook_url is None
    # Must not raise and must not attempt any POST.
    await gate.require(
        action="godot_scene_edit_delete_node", safety_class="destructive", params={"node_path": "X"}
    )


async def test_webhook_approval_passes() -> None:
    poster, seen = _poster(ApprovalResponse(approved=True))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster)
    await gate.require(
        action="godot_scene_edit_delete_node", safety_class="destructive", params={"node_path": "X"}
    )
    assert len(seen) == 1


async def test_webhook_denial_raises_precondition() -> None:
    poster, _ = _poster(ApprovalResponse(approved=False, reason="nope"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster)
    with pytest.raises(PreconditionError) as exc:
        await gate.require(
            action="godot_scene_edit_delete_node", safety_class="destructive", params={}
        )
    assert exc.value.error == "APPROVAL_DENIED"
    assert "nope" in exc.value.hint


async def test_request_payload_carries_context() -> None:
    poster, seen = _poster()
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, clock=lambda: 123.0)
    await gate.require(
        action="godot_scene_edit_delete_node",
        safety_class="destructive",
        params={"node_path": "Enemy"},
        task_context="cleanup",
    )
    req = seen[0]
    assert req.action == "godot_scene_edit_delete_node"
    assert req.safety_class == "destructive"
    assert req.params == {"node_path": "Enemy"}
    assert req.task_context == "cleanup"
    assert req.timestamp == 123.0


async def test_unreachable_webhook_fails_open_by_default() -> None:
    poster, _ = _poster(raises=TimeoutError("boom"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, fail_open=True)
    await gate.require(
        action="godot_scene_edit_delete_node", safety_class="destructive", params={}
    )  # no raise


async def test_unreachable_webhook_can_fail_closed() -> None:
    poster, _ = _poster(raises=TimeoutError("boom"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, fail_open=False)
    with pytest.raises(PreconditionError) as exc:
        await gate.require(
            action="godot_scene_edit_delete_node", safety_class="destructive", params={}
        )
    assert exc.value.error == "APPROVAL_DENIED"


async def test_from_config_reads_fields() -> None:
    config = ServerConfig(
        approval_webhook="http://hook", approval_timeout=5.0, approval_fail_open=False
    )
    gate = ApprovalGate.from_config(config)
    assert gate.webhook_url == "http://hook"
    assert gate.timeout == 5.0
    assert gate.fail_open is False
    assert gate.require_approval is False


async def test_from_config_reads_require_approval() -> None:
    config = ServerConfig(approval_require=True)
    gate = ApprovalGate.from_config(config)
    assert gate.require_approval is True


async def test_from_config_without_webhook_is_noop() -> None:
    gate = ApprovalGate.from_config(ServerConfig())
    assert gate.webhook_url is None
    await gate.require(action="godot_scene_edit_delete_node", safety_class="destructive", params={})


async def test_well_formed_response_parses() -> None:
    assert parse_approval_response({"approved": True}).approved is True
    # Missing field defaults to NOT approved (fail safe).
    assert parse_approval_response({"reason": "x"}).approved is False


async def test_malformed_response_fails_safe_to_denied() -> None:
    # Non-dict / wrong-shape bodies must deny, not raise or approve.
    for bad in ("approved", ["yes"], 42):
        assert parse_approval_response(bad).approved is False


async def test_malformed_response_denies_even_when_fail_open() -> None:
    # A *received* but unparseable verdict must not auto-approve even with
    # fail_open=True (that's only for unreachable webhooks).
    async def malformed(url: str, request: ApprovalRequest, timeout: float) -> ApprovalResponse:
        return parse_approval_response("garbage")

    gate = ApprovalGate(webhook_url="http://hook", poster=malformed, fail_open=True)
    with pytest.raises(PreconditionError) as exc:
        await gate.require(
            action="godot_scene_edit_delete_node", safety_class="destructive", params={}
        )
    assert exc.value.error == "APPROVAL_DENIED"


# --- guard pattern (issue #346) -------------------------------------------


async def test_build_input_required_request_state_carries_tool_and_params() -> None:
    # The durable round-trip depends on InputRequiredResult.request_state carrying
    # the tool name, safety_class, and params so a stateless client can re-call
    # the tool with the decision on the next round (issue #346).
    result = _build_input_required(
        "godot_scene_edit_create_node",
        "mutating",
        {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
    )
    state = result.input_required.request_state
    assert state is not None  # narrowed for mypy
    payload = json.loads(state)
    assert payload["tool"] == "godot_scene_edit_create_node"
    assert payload["safety_class"] == "mutating"
    assert payload["params"] == {
        "parent_path": ".",
        "node_type": "Node2D",
        "node_name": "Player",
    }


async def test_build_input_required_elicitation_asks_approve() -> None:
    # The elicitation request under APPROVE_KEY carries a yes/no schema the
    # client renders; its answer arrives in ctx.input_responses[APPROVE_KEY].
    result = _build_input_required(
        "godot_scene_edit_delete_node", "destructive", {"node_path": "Enemy"}
    )
    requests = result.input_required.input_requests
    assert requests is not None  # narrowed for mypy
    request = requests[APPROVE_KEY]
    params = request.params
    assert isinstance(params, ElicitRequestFormParams)  # form-mode elicitation
    # The schema requires a single boolean "approve" field.
    schema = params.requested_schema
    assert schema["properties"]["approve"]["type"] == "boolean"
    assert schema["required"] == ["approve"]
