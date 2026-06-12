#!/usr/bin/env python3
"""Dynamic corrective-prompt formatting for eval agents (issue #149).

Static system prompts get ignored after a few steps, so models repeat the same
failing call 2–3× before recovering. After a failure we append a compact, high
-attention correction to the *next user message* (not the system prompt) naming
the exact call that failed and telling the model to apply the hint instead of
repeating itself. Kept short to avoid token bloat.

Shared by OllamaAgent and CloudAgent so the wording can't drift between them.
"""

from __future__ import annotations

import json
from typing import Any

# Cap so the correction stays high-signal and cheap (issue #149 acceptance).
CORRECTION_LIMIT = 200


def format_correction(
    tool: str,
    params: dict[str, Any],
    error: str | None,
    hint: str | None,
    limit: int = CORRECTION_LIMIT,
) -> str:
    """Return a one-line correction (<= ``limit`` chars) for a failed call.

    Names the failed ``tool(params)`` plus the ``error``/``hint`` and instructs
    the model not to repeat the same parameters.
    """
    err = (error or "ERROR").strip()
    hint_str = (hint or "").strip()
    # Keep the call signature from crowding out the instruction: a large
    # payload (e.g. write_script `content`) is reduced to a short snippet.
    params_str = json.dumps(params, separators=(",", ":")) if params else "{}"
    if len(params_str) > 60:
        params_str = params_str[:57] + "..."
    # Lead with the error+hint (the actual fix) so it survives the cap even
    # when the call signature that follows is long.
    lead = f"CORRECTION ({err}): {hint_str}".rstrip()
    tail = f" Your last call was {tool}({params_str}); do NOT repeat the same parameters."
    return (lead + tail)[:limit]
