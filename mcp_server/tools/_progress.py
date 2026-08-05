"""Guarded Context progress helpers (issue #331).

``ctx.info`` / ``ctx.report_progress`` raise ``RuntimeError: session is not
available`` in the detached task input loop (``task=True``), because the
session back-channel is gone. These helpers no-op on that failure so
long-running tools can be task-enabled without losing progress for the
non-task path.
"""

from __future__ import annotations

from typing import Any


async def safe_info(ctx: Any, msg: str) -> None:
    try:
        await ctx.info(msg)
    except Exception:
        pass


async def safe_progress(ctx: Any, current: float, total: float) -> None:
    try:
        await ctx.report_progress(current, total)
    except Exception:
        pass
