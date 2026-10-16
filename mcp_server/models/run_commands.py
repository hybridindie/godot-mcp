"""Typed result models for the ``run_commands`` batch envelope (issue #167).

The addon executes a list of sub-commands in a single ``_process`` frame and
returns one response envelope per sub-command. Collapsing N round-trips into one
is the only real throughput lever for scripted harnesses, since the editor
drains commands serially on its main thread (~one frame of latency each).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunCommandEntry(BaseModel):
    """One ``{command, params}`` entry of a ``run_commands`` batch (issue #691:
    a typed shape so the schema guides client generation)."""

    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class SubCommandResult(BaseModel):
    """One sub-command's outcome within a ``run_commands`` batch.

    Mirrors the response envelope shape: ``ok`` plus either ``result`` (success)
    or ``error``/``hint`` (failure). ``command`` echoes the addon command so the
    caller can correlate results even when ``stop_on_error`` truncates the list.
    """

    command: str
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    hint: str | None = None


class SubCommandPlan(BaseModel):
    """A sub-command resolved back to the tool that backs it (issue #634).

    The batch's outer tool is ``mutating``, so each entry is mapped to its
    exposed tool to inherit that tool's toolset (gating), path preflight, and
    safety class (destructive needs ``confirm``). ``tool`` is ``None`` when the
    command backs no registered tool (an unknown ``cmd_*``).
    """

    command: str
    tool: str | None = None
    toolset: str | None = None
    safety_class: str | None = None


class RunCommandsResult(BaseModel):
    """Result of a ``run_commands`` batch executed in one editor frame.

    ``ok_all`` is True only when every sub-command succeeded; the batch envelope
    itself is still a success (the commands ran) even if individual sub-commands
    failed — inspect ``results`` for per-command status. ``dry_run`` returns the
    ``planned`` command names without executing anything.

    #461: when ``stop_on_error`` halted the batch early, ``aborted_at`` names
    the index of the failing sub-command and ``skipped_count``/``hint`` make the
    trailing work explicit (default ``stop_on_error=True`` means trailing
    commands — e.g. ``save_scene`` — silently never ran before this field).

    #634: ``plan`` resolves every entry back to its exposed tool, toolset, and
    safety class (empty when the batch failed policy validation before a plan
    could be produced).
    """

    results: list[SubCommandResult] = []
    ok_all: bool
    count: int
    planned: list[str] = []
    plan: list[SubCommandPlan] = []
    dry_run: bool = False
    aborted_at: int | None = None
    skipped_count: int = 0
    hint: str | None = None
