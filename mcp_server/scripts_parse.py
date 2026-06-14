"""Tool-independent parsing of Godot ``--check-only`` output.

Kept free of FastMCP / tool-layer imports so both the scripts tool and the
debug-workflow service can use it without pulling in tool-registration code.
"""

from __future__ import annotations

import re

from mcp_server.models.scripts import ParseError

# "(res://path.gd:42)" as printed on a parse error's "at:" line.
_CHECK_SOURCE_RE = re.compile(r"\((res://[^):]+):(\d+)\)")


def parse_check_errors(text: str) -> list[ParseError]:
    """Extract structured parse errors from ``--check-only`` output.

    Godot prints ``SCRIPT ERROR: Parse Error: <message>`` followed by an
    ``at: … (res://file.gd:LINE)`` line; pair them up.
    """
    lines = text.splitlines()
    errors: list[ParseError] = []
    for i, line in enumerate(lines):
        # Only genuine parse errors — not other SCRIPT ERROR shapes (e.g. load
        # failures) that --check-only may also print.
        if "Parse Error:" not in line:
            continue
        message = line.split("Parse Error:", 1)[-1].strip()
        source: str | None = None
        line_no: int | None = None
        for look in lines[i : i + 3]:
            match = _CHECK_SOURCE_RE.search(look)
            if match:
                source, line_no = match.group(1), int(match.group(2))
                break
        errors.append(ParseError(message=message, source=source, line=line_no))
    return errors
