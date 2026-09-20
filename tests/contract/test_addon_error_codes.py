"""Contract test: the addon's error codes stay a subset of the Python ErrorCode
enum (issue #525).

The authoritative error-code set is ``ErrorCode`` in
``mcp_server/models/envelope.py`` (rule: never invent a new error code outside
the enumerated set). The addon emits codes as raw strings at ``_fail(...)``
call sites and in structured-error dicts (e.g. ``type_coerce.object_from_json``)
because GDScript has no importable copy of the enum. Nothing else ties the two
surfaces together — a typo'd or invented code would flow through to clients
undetected.

This test source-scans ``godot/addons/godot_mcp/**/*.gd`` (same technique as
``test_rename_refusal.py`` — the addon is GDScript, only runnable inside Godot)
and asserts every emitted error code is a member of the Python enum.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp_server.models.envelope import ErrorCode

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"

ALLOWED = {member.value for member in ErrorCode}

# Codes that are envelope-conformant but *only* appear inside nested payload
# dicts (not the envelope's own `error` field). Kept explicit so additions are
# deliberate, not accidental — a new nested code must be added here with a
# comment naming the consumer.
NESTED_ALLOWED: set[str] = set()

# Matches the first argument of the router's _fail(...) builder at every call
# site (the router's own definition passes through variable args and is
# excluded below). String literals only; the enum-table form (const ErrorCode)
# is checked separately once it exists.
_FAIL_CALL = re.compile(r'_fail\(\s*"([A-Z_]+)"')


def _gd_files() -> list[Path]:
    return sorted(ADDON_DIR.rglob("*.gd"))


def _collect_codes() -> dict[str, list[str]]:
    """Map each emitted error-code literal to the files that emit it."""
    found: dict[str, list[str]] = {}
    for path in _gd_files():
        src = path.read_text()
        rel = path.relative_to(REPO_ROOT)
        for code in _FAIL_CALL.findall(src):
            found.setdefault(code, []).append(f"{rel} (_fail)")
        for match in re.finditer(r'"error":\s*"([A-Z_]+)"', src):
            code = match.group(1)
            if code in ALLOWED:
                found.setdefault(code, []).append(f"{rel} (envelope)")
    return found


def test_addon_emits_only_enumerated_error_codes() -> None:
    found = _collect_codes()
    unknown = {
        code: locs
        for code, locs in found.items()
        if code not in ALLOWED and code not in NESTED_ALLOWED
    }
    assert not unknown, (
        "Addon emits error codes outside the ErrorCode enum "
        f"(mcp_server/models/envelope.py): {unknown}. "
        "Error codes are a closed set — use an enumerated code, or extend the "
        "Python enum deliberately (rule: error-handling.md)."
    )


def test_every_python_error_code_is_used_or_explicitly_unrepresented() -> None:
    """Drift check in the other direction: a code in the Python enum but never
    emitted by the addon is fine (server-side codes like BRIDGE_DISCONNECTED /
    TIMEOUT / APPROVAL_DENIED are synthesized server-side), but this test pins
    that awareness — update the sets below when the enum grows."""
    server_only = {
        "BRIDGE_DISCONNECTED",  # synthesized by the server on send-without-peer
        "TIMEOUT",  # synthesized by the server on request timeout
        "APPROVAL_DENIED",  # human-in-the-loop gate (#153), server-side middleware
    }
    emitted = set(_collect_codes())
    unused = ALLOWED - emitted - server_only
    assert not unused, (
        f"ErrorCode members neither emitted by the addon nor accounted for as "
        f"server-only: {unused}. If a new code is server-only, list it in "
        f"`server_only` here; if the addon should emit it, wire it up."
    )