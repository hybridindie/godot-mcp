"""Unit: the guard-pattern approval is bound to the call it approved (#346 follow-up).

The first round seals ``{tool, safety_class, params}`` into ``request_state``,
but the continuation round only reads ``input_responses["approve"]``. An
approval for one set of arguments therefore authorizes any other set.
"""

from __future__ import annotations

import json
import secrets
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from mcp_server.approval_middleware import APPROVE_KEY, ApprovalMiddleware, seal_request_state
from mcp_server.safety import ApprovalGate

pytestmark = pytest.mark.asyncio


class _Server:
    async def get_tool(self, name: str) -> Any:
        return SimpleNamespace(name=name, meta={"safety_class": "mutating"}, parameters={})


def _context(*, arguments: dict[str, Any], request_state: str | None) -> Any:
    accepted = SimpleNamespace(action="accept", content={"approve": True})
    fctx = SimpleNamespace(
        fastmcp=_Server(),
        input_responses={APPROVE_KEY: accepted},
        request_state=request_state,
    )
    message = SimpleNamespace(name="godot_scene_edit_create_node", arguments=arguments)
    return SimpleNamespace(message=message, fastmcp_context=fctx)


# The binding-failure denial, as opposed to a human declining the approval.
_MISMATCH = "does not match the approved call"
_TOOL = "godot_scene_edit_create_node"
_ARGS = {"parent_path": ".", "node_type": "Node2D", "node_name": "X"}


def _sealed(
    middleware: ApprovalMiddleware,
    params: dict[str, Any],
    *,
    key: bytes | None = None,
    tool: str = _TOOL,
    safety_class: str = "mutating",
) -> str:
    """A correctly signed, unexpired, unused state, so each test varies one field."""
    payload = {
        "tool": tool,
        "safety_class": safety_class,
        "params": params,
        "exp": time.time() + 120.0,
        "nonce": secrets.token_urlsafe(12),
    }
    return seal_request_state(key or middleware._state_key, payload)  # noqa: SLF001


async def _first_round_state(middleware: ApprovalMiddleware, arguments: dict[str, Any]) -> str:
    """Seal state through the real first round (no input responses yet)."""
    context = _context(arguments=arguments, request_state=None)
    context.fastmcp_context.input_responses = None

    async def call_next(_ctx: Any) -> str:
        raise AssertionError("the first round must ask, not run")

    result = await middleware.on_call_tool(context, call_next)
    state = result.input_required.request_state
    assert isinstance(state, str)
    return state


async def _run(middleware: ApprovalMiddleware, context: Any) -> list[bool]:
    ran: list[bool] = []

    async def call_next(_ctx: Any) -> str:
        ran.append(True)
        return "ran"

    await middleware.on_call_tool(context, call_next)
    return ran


async def test_approval_for_other_arguments_does_not_run_the_tool() -> None:
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    # Correctly sealed for the approved call, so only the tool/params binding
    # can refuse the continuation (not the signature check).
    approved_state = _sealed(
        middleware, {"parent_path": ".", "node_type": "Node2D", "node_name": "Harmless"}
    )
    context = _context(
        arguments={"parent_path": ".", "node_type": "Node2D", "node_name": "Different"},
        request_state=approved_state,
    )
    ran: list[bool] = []

    async def call_next(_ctx: Any) -> str:
        ran.append(True)
        return "ran"

    with pytest.raises(ToolError, match=_MISMATCH):
        await middleware.on_call_tool(context, call_next)
    assert ran == []


async def test_continuation_without_request_state_does_not_run_the_tool() -> None:
    context = _context(
        arguments={"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
        request_state=None,
    )
    ran: list[bool] = []

    async def call_next(_ctx: Any) -> str:
        ran.append(True)
        return "ran"

    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    with pytest.raises(ToolError, match=_MISMATCH):
        await middleware.on_call_tool(context, call_next)
    assert ran == []


async def test_matching_sealed_state_runs_the_tool() -> None:
    """Positive control: the denials above are about the binding, not over-broad."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    context = _context(arguments=dict(_ARGS), request_state=_sealed(middleware, dict(_ARGS)))
    assert await _run(middleware, context) == [True]


async def test_state_signed_with_another_key_does_not_run_the_tool() -> None:
    """Same tool and params, wrong key: only the signature check can refuse it."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    forged = _sealed(middleware, dict(_ARGS), key=b"\x00" * 32)
    context = _context(arguments=dict(_ARGS), request_state=forged)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_non_ascii_signature_is_a_structured_denial() -> None:
    """A client-controlled non-ASCII ``sig`` must deny like any tampering, not
    raise TypeError out of hmac.compare_digest."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    state = _sealed(middleware, dict(_ARGS)).replace('"sig": "', '"sig": "caf\u00e9')
    context = _context(arguments=dict(_ARGS), request_state=state)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_approval_for_other_tool_does_not_run_the_tool() -> None:
    """Identical args, different tool: only the tool half of the binding refuses it."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    state = _sealed(middleware, dict(_ARGS), tool="godot_scene_edit_rename_node")
    context = _context(arguments=dict(_ARGS), request_state=state)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_state_sealed_for_another_safety_class_does_not_run_the_tool() -> None:
    """The sealed class must equal the class recomputed for the continuation."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    state = _sealed(middleware, dict(_ARGS), safety_class="read_only")
    context = _context(arguments=dict(_ARGS), request_state=state)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_first_use_of_a_sealed_state_runs_the_tool() -> None:
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    state = await _first_round_state(middleware, dict(_ARGS))
    context = _context(arguments=dict(_ARGS), request_state=state)
    assert await _run(middleware, context) == [True]


async def test_replayed_state_does_not_run_the_tool_twice() -> None:
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    state = await _first_round_state(middleware, dict(_ARGS))
    assert await _run(middleware, _context(arguments=dict(_ARGS), request_state=state)) == [True]
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, _context(arguments=dict(_ARGS), request_state=state))


async def test_expired_state_does_not_run_the_tool() -> None:
    now = [1_000.0]
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True), clock=lambda: now[0])
    state = await _first_round_state(middleware, dict(_ARGS))
    now[0] += 121.0
    context = _context(arguments=dict(_ARGS), request_state=state)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_lone_surrogate_signature_is_a_structured_denial() -> None:
    """json.loads accepts "\\ud800"; it must deny, not raise UnicodeEncodeError."""
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    payload = json.loads(_sealed(middleware, dict(_ARGS)))
    payload["sig"] = "\ud800"
    context = _context(arguments=dict(_ARGS), request_state=json.dumps(payload))
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)


async def test_deeply_nested_state_is_a_structured_denial() -> None:
    """json.loads raises RecursionError on deep nesting; it must deny instead.

    The depth must exceed the C decoder's own limit (5000 levels still parses on
    CPython 3.13), or the test never reaches the RecursionError path.
    """
    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    depth = 100_000
    context = _context(arguments=dict(_ARGS), request_state="[" * depth + "]" * depth)
    with pytest.raises(ToolError, match=_MISMATCH):
        await _run(middleware, context)
