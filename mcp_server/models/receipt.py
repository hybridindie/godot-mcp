"""Change receipts for mutating results (issue #756).

A mutating tool can return ``ok`` while the scene/project did not change. The
receipt is the addon's read-back after the mutation: ``status`` says what
happened, ``changes`` lists the paths that actually changed (bounded, with an
honest ``truncated`` flag). It is additive to the persistence verdict: persistence
answers "will this survive save?", the receipt answers "what changed now?".
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReceiptStatus(StrEnum):
    """What the mutation actually did, from the addon's read-back."""

    CREATED = "created"
    UPDATED = "updated"
    # The target already matched the request (an idempotent re-run).
    EXISTED = "existed"
    # The request was accepted but nothing changed (e.g. a silently dropped write).
    NOOP = "noop"


class ChangeOp(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    SET = "set"
    WRITE = "write"
    RENAME = "rename"


class Change(BaseModel):
    """One changed path. ``path`` is a node path or a ``res://`` file path."""

    path: str
    op: ChangeOp
    before: Any = None
    after: Any = None


class ChangeReceipt(BaseModel):
    """The bounded change list plus its status (#756)."""

    status: ReceiptStatus
    changes: list[Change] = Field(default_factory=list)
    truncated: bool = False
