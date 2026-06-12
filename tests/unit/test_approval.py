"""Human-in-the-loop approval gate for destructive tools (issue #153).

The gate is opt-in: with no webhook configured it auto-approves (so evals and
headless runs are never blocked). When a webhook is set, destructive tools must
be approved; unreachable webhooks fail open or closed per config. The HTTP
poster is injected, so this is a pure unit test — no network.
"""

from __future__ import annotations

import pytest

from mcp_server.config import ServerConfig
from mcp_server.models.approval import ApprovalRequest, ApprovalResponse
from mcp_server.safety import ApprovalGate, ApprovalPoster, PreconditionError

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
    await gate.require(action="delete_node", safety_class="destructive", params={"node_path": "X"})


async def test_webhook_approval_passes() -> None:
    poster, seen = _poster(ApprovalResponse(approved=True))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster)
    await gate.require(action="delete_node", safety_class="destructive", params={"node_path": "X"})
    assert len(seen) == 1


async def test_webhook_denial_raises_precondition() -> None:
    poster, _ = _poster(ApprovalResponse(approved=False, reason="nope"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster)
    with pytest.raises(PreconditionError) as exc:
        await gate.require(action="delete_node", safety_class="destructive", params={})
    assert exc.value.error == "APPROVAL_DENIED"
    assert "nope" in exc.value.hint


async def test_request_payload_carries_context() -> None:
    poster, seen = _poster()
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, clock=lambda: 123.0)
    await gate.require(
        action="delete_node",
        safety_class="destructive",
        params={"node_path": "Enemy"},
        task_context="cleanup",
    )
    req = seen[0]
    assert req.action == "delete_node"
    assert req.safety_class == "destructive"
    assert req.params == {"node_path": "Enemy"}
    assert req.task_context == "cleanup"
    assert req.timestamp == 123.0


async def test_unreachable_webhook_fails_open_by_default() -> None:
    poster, _ = _poster(raises=TimeoutError("boom"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, fail_open=True)
    await gate.require(action="delete_node", safety_class="destructive", params={})  # no raise


async def test_unreachable_webhook_can_fail_closed() -> None:
    poster, _ = _poster(raises=TimeoutError("boom"))
    gate = ApprovalGate(webhook_url="http://hook", poster=poster, fail_open=False)
    with pytest.raises(PreconditionError) as exc:
        await gate.require(action="delete_node", safety_class="destructive", params={})
    assert exc.value.error == "APPROVAL_DENIED"


async def test_from_config_reads_fields() -> None:
    config = ServerConfig(
        approval_webhook="http://hook", approval_timeout=5.0, approval_fail_open=False
    )
    gate = ApprovalGate.from_config(config)
    assert gate.webhook_url == "http://hook"
    assert gate.timeout == 5.0
    assert gate.fail_open is False


async def test_from_config_without_webhook_is_noop() -> None:
    gate = ApprovalGate.from_config(ServerConfig())
    assert gate.webhook_url is None
    await gate.require(action="delete_node", safety_class="destructive", params={})
