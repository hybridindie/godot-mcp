"""The versioned JSON envelope crossing the bridge (issue #3).

Command (server → addon): ``{ id, command, params }``.
Response (addon → server): ``{ id, ok, result }`` or
``{ id, ok: false, error, hint[, required] }``.

See docs/architecture.md and .claude/rules/error-handling.md. Error codes are a
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
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


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
    ) -> ResponseEnvelope:
        return cls(
            id=id,
            ok=False,
            error=str(error.value if isinstance(error, ErrorCode) else error),
            hint=hint,
            required=required,
        )

    def model_dump_json(self, **kwargs: Any) -> str:
        # Drop null fields so success/failure envelopes match the documented
        # wire shapes exactly (no result:null on success, no error:null, etc.).
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)
