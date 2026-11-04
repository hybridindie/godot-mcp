"""Classify the connected Godot engine against the server's support surface.

The MCP already reports the engine it is *actually* attached to (the addon's
``Engine.get_version_info().string`` in the bridge handshake). This module turns
that raw string into a support status, so an agent can tell three cases apart:

* the **validated** stable target (currently 4.7),
* an engine that is merely **supported** (4.4–4.6), and
* a **prerelease** or **newer** engine, which is reported honestly instead of
  being silently treated as validated.

``VERIFIED_AGAINST`` names the newest Godot prerelease this build is verified
against on the advisory lane. It is deliberately separate from ``VALIDATED``:
a beta is a verification target, not a supported release.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

#: Oldest editor the addon parses and runs on (``MIN_GODOT_*`` in godot_mcp.gd).
FLOOR = (4, 4)
#: The stable engine the project is validated against (``config/features``).
VALIDATED = (4, 7)
#: Newest Godot prerelease verified on the advisory e2e lane (#842).
VERIFIED_AGAINST = "4.8-beta2"

Status = Literal[
    "disconnected",
    "unknown",
    "below_floor",
    "supported",
    "validated",
    "prerelease",
    "newer",
]

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")
_PRERELEASE_RE = re.compile(r"(?:^|[.\-])(alpha|beta|rc|dev)[.\-]?(\d*)", re.IGNORECASE)


class GodotSupportInfo(BaseModel):
    """How the connected engine relates to what this build supports."""

    detected: str | None = None
    status: Status = "disconnected"
    floor: str = "4.4"
    validated: str = "4.7"
    #: The Godot prerelease this build is verified against (advisory lane).
    verified_against: str = VERIFIED_AGAINST
    notice: str | None = None


def _label(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def classify_godot_version(version: str | None) -> GodotSupportInfo:
    """Classify a Godot ``--version`` string (e.g. ``4.7.2-stable (official)``).

    Pure and total: an unknown or malformed string never raises, it reports
    ``unknown`` with an actionable notice. A missing version (no editor) reports
    ``disconnected``, which is not an error.
    """
    if not version:
        return GodotSupportInfo()

    match = _VERSION_RE.match(version.strip())
    if not match:
        return GodotSupportInfo(
            detected=version,
            status="unknown",
            notice=(
                f"Unrecognised Godot version string {version!r}; support cannot be "
                "determined. Compare it with the validated target manually."
            ),
        )

    major, minor = int(match.group(1)), int(match.group(2))
    engine = (major, minor)
    floor, validated = _label(FLOOR), _label(VALIDATED)
    prerelease = _PRERELEASE_RE.search(version)

    if engine < FLOOR:
        return GodotSupportInfo(
            detected=version,
            status="below_floor",
            notice=(
                f"Godot {version} is below the supported floor ({floor}). Upgrade "
                "the editor; addon handlers may fail or refuse to load."
            ),
        )

    if prerelease:
        kind = prerelease.group(1).lower()
        return GodotSupportInfo(
            detected=version,
            status="prerelease",
            notice=(
                f"Godot {version} is a {kind} prerelease. This build is verified "
                f"against {VERIFIED_AGAINST} on the advisory lane, but {validated} "
                "remains the validated stable target — results may differ."
            ),
        )

    if engine == VALIDATED:
        return GodotSupportInfo(detected=version, status="validated")

    if engine > VALIDATED:
        return GodotSupportInfo(
            detected=version,
            status="newer",
            notice=(
                f"Godot {version} is newer than the validated target ({validated}). "
                f"This build is verified against {VERIFIED_AGAINST}; report anything "
                "that behaves differently."
            ),
        )

    return GodotSupportInfo(detected=version, status="supported")
