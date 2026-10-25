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
and asserts every emitted error code is a member of the Python enum. The scan
covers both call layouts the addon uses (code literal on the same line as
``_fail(`` and the wrapped form with the literal on the next line) plus the
``"error": "CODE"`` dict form in ``type_coerce.gd``.
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
# site, in both layouts used by the addon: the code literal on the same line
# as `_fail(` and the wrapped form with the literal on the next line(s)
# (DOTALL across the opening paren + whitespace/newlines; the router's own
# definition passes through variable args and is excluded by the literal-only
# match). Only string literals are scanned — a variable/const code reference
# would evade it, but none exist today and the enum-table direction (issue
# #525's optional item 1) is the durable fix once the addon adopts one.
_FAIL_CALL = re.compile(r'_fail\(\s*"([A-Z_]+)"')


def _gd_files() -> list[Path]:
    return sorted(ADDON_DIR.rglob("*.gd"))


def _collect_codes() -> dict[str, list[str]]:
    """Map each emitted error-code literal to the files that emit it."""
    found: dict[str, list[str]] = {}
    for path in _gd_files():
        src = path.read_text()
        rel = path.relative_to(REPO_ROOT)
        # _fail("CODE", ...) and the wrapped form `_fail(\n\t\t"CODE", ...` —
        # DOTALL bridges the newline; \s* consumes tabs/spaces after it.
        for match in re.finditer(r'_fail\(\s*"([A-Z_]+)"', src):
            found.setdefault(match.group(1), []).append(f"{rel} (_fail)")
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
        "PEER_REPLACED",  # server notice to a replaced peer (#593); the addon only
        # *reads* this code (never emits it via _fail), so the _fail scan misses it
        "UNDECLARED_PARAMETER",  # server-side argument validation (#757)
        "CONSENT_MISMATCH",  # server-side consent-token verification (#759)
        "EDITOR_BUSY",  # server-side readiness gate (#762)
        "PARAM_ERROR",  # server-side path/shape validation before the bridge (#791)
        "OUTPUT_LIMIT",  # server-side 25k payload cap (#791)
        "DOWNLOAD_FAILED",  # server-side remote-asset fetch failure (#791)
    }
    emitted = set(_collect_codes())
    unused = ALLOWED - emitted - server_only
    assert not unused, (
        f"ErrorCode members neither emitted by the addon nor accounted for as "
        f"server-only: {unused}. If a new code is server-only, list it in "
        f"`server_only` here; if the addon should emit it, wire it up."
    )


# Python-side scan (#791): the mirror of the addon scan above. A server-side
# literal that isn't in the enum is the same drift bug — it just lives in the
# other language. Covers the two shapes the server uses: any exception class
# whose first argument is a code literal, and a `"error": "CODE"` dict.
#
# The literal must be a standalone code (`CODE: …` or the whole argument); that
# check is what keeps an ordinary message like
# `ValueError("HTTP transport requires …")` out of the set.
_PY_ERROR_CALL = re.compile(r'\b\w*(?:Error|Exception)\(\s*f?["\']([A-Z][A-Z_]{3,})')
_PY_ERROR_DICT = re.compile(r'"error":\s*"([A-Z][A-Z_]{3,})"')


def _collect_server_codes() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "mcp_server").rglob("*.py")):
        rel = str(path.relative_to(REPO_ROOT))
        src = path.read_text()
        for match in _PY_ERROR_CALL.finditer(src):
            if src[match.end(1) : match.end(1) + 1] not in (":", "'", '"'):
                continue
            found.setdefault(match.group(1), []).append(rel)
        for match in _PY_ERROR_DICT.finditer(src):
            found.setdefault(match.group(1), []).append(rel)
    return found


def test_server_emits_only_enumerated_error_codes() -> None:
    """The Python half of the same closed-set rule (#791)."""
    found = _collect_server_codes()
    unknown = {code: locs for code, locs in found.items() if code not in ALLOWED}
    assert not unknown, (
        f"Server emits error codes outside the ErrorCode enum: {unknown}. "
        "Add the code to mcp_server/models/envelope.py deliberately, or reuse "
        "an existing one (rule: error-handling.md)."
    )