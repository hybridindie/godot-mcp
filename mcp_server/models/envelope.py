"""The versioned JSON envelope crossing the bridge (issue #3).

Command (server → addon): ``{ id, command, params }``.
Response (addon → server): ``{ id, ok, result }`` or
``{ id, ok: false, error, hint[, required] }``.

See docs/architecture.md and .opencode/rules/error-handling.md. Error codes are a
closed set — never invent ad-hoc strings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """The enumerated, stable error codes (docs/architecture.md)."""

    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BRIDGE_DISCONNECTED = "BRIDGE_DISCONNECTED"
    # #593: a server-initiated notice to a peer that was replaced by another
    # editor (best-effort, delivered just before the old peer is closed). The
    # replacement itself is not an error — the code names WHY the old peer went
    # dark so the replaced editor's dock can stop showing a green "Connected".
    PEER_REPLACED = "PEER_REPLACED"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    APPROVAL_DENIED = "APPROVAL_DENIED"  # human-in-the-loop gate (issue #153)
    # #677: the requested capability exists but the connected Godot version/engine
    # cannot provide it (e.g. the paused-frame stack/eval protocol is not exposed to
    # editor debugger plugins on 4.7). Honest, not a silent empty result.
    UNSUPPORTED = "UNSUPPORTED"
    # #647: a reply was too large for the addon's outbound buffer and was dropped —
    # surfaced instead of letting the server time out with no cause.
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    # #757: a tool call included an argument the tool does not declare. Rejected
    # instead of silently dropped, with the accepted names + a corrected next_call.
    UNDECLARED_PARAMETER = "UNDECLARED_PARAMETER"
    # #759: a destructive call's consent token is missing, expired, replayed, or
    # does not match the exact (tool, args) it was minted for.
    CONSENT_MISMATCH = "CONSENT_MISMATCH"


class NextCall(BaseModel):
    """A fully-formed follow-up call the client can send as-is (#757).

    ``reason`` is a short human explanation (e.g. "enable the scene_edit toolset").
    """

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class CommandEnvelope(BaseModel):
    """A command sent from the server to the addon."""

    id: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    """A response from the addon (or a server-synthesized transport error).

    Lenient on input (ignores unknown fields from the addon for forward
    compatibility); ``success``/``failure`` build the canonical shapes.
    """

    id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    hint: str | None = None
    required: str | None = None
    # #757: an optional, fully-formed recovery call (from the addon or the server).
    next_call: NextCall | None = None

    @classmethod
    def success(cls, id: str, result: dict[str, Any] | None = None) -> ResponseEnvelope:
        return cls(id=id, ok=True, result=result)

    @classmethod
    def failure(
        cls,
        id: str,
        error: str | ErrorCode,
        hint: str,
        required: str | None = None,
        next_call: NextCall | dict[str, Any] | None = None,
    ) -> ResponseEnvelope:
        return cls(
            id=id,
            ok=False,
            error=str(error.value if isinstance(error, ErrorCode) else error),
            hint=hint,
            required=required,
            next_call=(
                next_call
                if isinstance(next_call, NextCall) or next_call is None
                else NextCall(**next_call)
            ),
        )

    def model_dump_json(self, **kwargs: Any) -> str:
        # Drop null fields so success/failure envelopes match the documented
        # wire shapes exactly (no result:null on success, no error:null, etc.).
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)
