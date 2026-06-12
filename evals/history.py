#!/usr/bin/env python3
"""History compression for eval agents (issue #148).

After ~8 steps the prompt grows past 5k tokens; quality degrades and the
480b-cloud model hit the 120s HTTP timeout. We keep the raw history internally
but send a compact, template-built summary of the older steps (no extra LLM
call) plus the most recent steps verbatim.

Shared by OllamaAgent and CloudAgent so the format can't drift.
"""

from __future__ import annotations

import json
from typing import Any

# Compress once the agent has taken more than this many steps (assistant turns).
COMPRESSION_THRESHOLD = 6
# Steps kept verbatim after the summary so the model still sees recent detail.
KEEP_RECENT_STEPS = 2


def char_len(messages: list[dict[str, Any]]) -> int:
    """Total character length of message contents — a cheap token proxy."""
    return sum(len(str(m.get("content", ""))) for m in messages)


def _parse_call(content: str) -> str | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    tool = data.get("tool")
    if not tool:
        return None
    params = data.get("params", {})
    params_str = json.dumps(params, separators=(",", ":")) if params else "{}"
    if len(params_str) > 60:
        params_str = params_str[:57] + "..."
    return f"{tool}({params_str})"


def _parse_result(content: str) -> tuple[bool, str]:
    # User result messages look like ``Tool result: {json}`` (optionally with a
    # trailing correction line). Pull the JSON object out and read ok/error/hint.
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return True, ""
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return True, ""
    ok = bool(data.get("ok", True))
    if ok:
        return True, ""
    err = (data.get("error") or "ERROR").strip()
    hint = (data.get("hint") or "").strip()
    return False, f"{err}: {hint}".strip().rstrip(":").strip()


def summarize_history(messages: list[dict[str, Any]]) -> str:
    """Template summary (no LLM): one line per completed step, ✓/✗ + hint."""
    lines = ["Progress summary (older steps compressed):"]
    pending: str | None = None
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            pending = _parse_call(str(m.get("content", "")))
        elif role == "user" and pending is not None:
            ok, detail = _parse_result(str(m.get("content", "")))
            mark = "✓" if ok else "✗"
            line = f"- {mark} {pending}"
            if not ok and detail:
                line += f" FAILED: {detail}"
            lines.append(line)
            pending = None
    return "\n".join(lines)


def compress_history(
    history: list[dict[str, Any]],
    threshold: int = COMPRESSION_THRESHOLD,
    keep_recent_steps: int = KEEP_RECENT_STEPS,
) -> list[dict[str, Any]]:
    """Return a sendable view: summary of older steps + the recent steps verbatim.

    Returns ``history`` unchanged when there are ``threshold`` steps or fewer.
    Never mutates the input — the caller keeps the raw history.
    """
    assistant_idx = [i for i, m in enumerate(history) if m.get("role") == "assistant"]
    if len(assistant_idx) <= threshold:
        return history
    cut = assistant_idx[len(assistant_idx) - keep_recent_steps]
    older, recent = history[:cut], history[cut:]
    summary = {"role": "user", "content": summarize_history(older)}
    return [summary, *recent]
