"""Consent-token result model (issue #759)."""

from __future__ import annotations

from pydantic import BaseModel


class ConsentToken(BaseModel):
    """The token ``describe_tool`` mints for a destructive call.

    ``consent_required`` is false for read-only/mutating tools (no token); those
    calls keep their normal safety class and never need one.
    """

    tool: str
    consent_required: bool = False
    token: str | None = None
    expires_at: float | None = None
    hint: str | None = None
