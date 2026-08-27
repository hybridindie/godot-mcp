"""Regression: approval middleware must use ErrorCode.APPROVAL_DENIED, not a
string literal (issue #368).

`PreconditionError.__init__` accepts ``ErrorCode | str``, so both type-check,
but the enum form is the convention (every other call site uses it). A string
literal is a drift risk: rename the enum value and this site silently keeps
the old string while ``safety.py`` stays correct.
"""

from __future__ import annotations

import inspect

from mcp_server.approval_middleware import ApprovalMiddleware
from mcp_server.models.envelope import ErrorCode


def test_guard_round_uses_errorcode_enum() -> None:
    """The ``PreconditionError`` raised on guard denial must use
    ``ErrorCode.APPROVAL_DENIED``, not the string literal ``"APPROVAL_DENIED"``.

    Inspects the source of ``ApprovalMiddleware._guard_round`` (the only place
    the middleware raises a denial) and asserts the ``error=`` kwarg is the
    enum, not a bare string.
    """
    src = inspect.getsource(ApprovalMiddleware._guard_round)
    # The enum member must appear in the source.
    assert "ErrorCode.APPROVAL_DENIED" in src, (
        "ApprovalMiddleware._guard_round must use ErrorCode.APPROVAL_DENIED, "
        "not the string literal 'APPROVAL_DENIED' (issue #368)."
    )
    # And the bare string literal must NOT appear as the error= value.
    # Match `error="APPROVAL_DENIED"` (with quotes) to catch the bug; the enum
    # form `ErrorCode.APPROVAL_DENIED` does not contain a quoted string.
    assert 'error="APPROVAL_DENIED"' not in src, (
        "ApprovalMiddleware._guard_round passes error=\"APPROVAL_DENIED\" "
        "(string literal) instead of ErrorCode.APPROVAL_DENIED (issue #368)."
    )


def test_errorcode_approval_denied_is_str_enum() -> None:
    """Sanity: the enum value still serializes to the stable string so the
    wire envelope is unchanged after the fix."""
    assert ErrorCode.APPROVAL_DENIED == "APPROVAL_DENIED"
    assert isinstance(ErrorCode.APPROVAL_DENIED, ErrorCode)