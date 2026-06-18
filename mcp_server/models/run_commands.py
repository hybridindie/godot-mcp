"""Typed result models for the ``run_commands`` batch envelope (issue #167).

The addon executes a list of sub-commands in a single ``_process`` frame and
returns one response envelope per sub-command. Collapsing N round-trips into one
is the only real throughput lever for scripted harnesses, since the editor
drains commands serially on its main thread (~one frame of latency each).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


class RunCommandsResult(BaseModel):
    """Result of a ``run_commands`` batch executed in one editor frame.

    ``ok_all`` is True only when every sub-command succeeded; the batch envelope
    itself is still a success (the commands ran) even if individual sub-commands
    failed — inspect ``results`` for per-command status. ``dry_run`` returns the
    ``planned`` command names without executing anything.
    """

    results: list[SubCommandResult] = []
    ok_all: bool
    count: int
    planned: list[str] = []
    dry_run: bool = False
