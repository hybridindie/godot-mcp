"""CalVer comparison and server↔addon version-drift notices (issue #629).

Versions are CalVer ``YYYY.MM.DD[-N]``. Comparing them as strings is unsafe (a
zero-padded and an unpadded build sort wrongly), so parse the numeric parts.
"""

from __future__ import annotations

import re

_LEADING_INT = re.compile(r"^\d+")


def parse_calver(value: str) -> tuple[int, ...] | None:
    """Parse ``YYYY.MM.DD[-N]`` (or a bare tag like ``v2026.10.10``) into its
    numeric parts, or ``None`` when it is not CalVer-shaped."""
    text = value.strip().lstrip("vV")
    if not text:
        return None
    head = text.split("-", 1)[0]
    parts: list[int] = []
    for part in head.split("."):
        match = _LEADING_INT.match(part)
        if not match:
            return None
        parts.append(int(match.group(0)))
    return tuple(parts) if parts else None


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a strictly newer CalVer than ``current``.

    Returns ``False`` when either side is unparseable — an unknown comparison
    must never claim an update exists.
    """
    a = parse_calver(candidate)
    b = parse_calver(current)
    if a is None or b is None:
        return False
    return a > b


def version_notice(server_version: str, addon_version: str | None) -> str | None:
    """A hint when the connected addon's version differs from the server's.

    ``None`` when they match, or when the addon version is unknown (a
    pre-handshake addon — nothing to compare, not an error).
    """
    if not addon_version or addon_version == server_version:
        return None
    behind = "addon" if is_newer(server_version, addon_version) else "server"
    return (
        f"SERVER↔ADDON VERSION MISMATCH: server {server_version} vs addon "
        f"{addon_version}. The {behind} is behind. Update both sides to the same "
        "release — pip-install the matching godot-mcp and install the addon from "
        "the same release (or copy godot/addons/godot_mcp/)."
    )
