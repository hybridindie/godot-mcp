"""Consent tokens bound to exact destructive args (issue #759).

A destructive call's ``confirm=True`` is an accident guard, not a security gate:
the agent sets it itself. A consent token is minted by ``describe_tool`` over the
exact ``(tool, canonical args)`` the caller intends, with a short expiry. The
call must present that token; any changed arg, expiry or replay is refused.

The manager is stateless except for the used-nonce set (replay prevention); it
lives in the server process. With no configured secret a random key is generated
at startup (tokens then do not survive a restart — acceptable for a short-lived
local token).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

# Set by ConsentMiddleware after a webhook-minted token is verified, so the
# inner ApprovalMiddleware does not ask the same human twice for one call.
APPROVAL_PRECLEARED: ContextVar[bool] = ContextVar(
    "godot_mcp_approval_precleared", default=False
)

# Args that are not part of the *effect* being consented to: ``consent`` is the
# token itself and ``confirm`` is the accident guard injected on success.
_IGNORED = ("consent", "confirm")
_MALFORMED = "Consent token is malformed; call describe_tool again."


class ConsentError(Exception):
    """A consent token failed verification; ``reason`` is a stable token."""

    def __init__(self, reason: str, hint: str) -> None:
        self.reason = reason
        self.hint = hint
        super().__init__(hint)


def canonical_args(args: dict[str, Any]) -> str:
    """The canonical effect args (stable across dict ordering and whitespace)."""
    cleaned = {k: v for k, v in args.items() if k not in _IGNORED}
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class ConsentManager:
    """Mint and verify HMAC consent tokens (#759)."""

    # Cap the replay set so a client that mints/verifies a flood of tokens cannot
    # grow it without bound; expired entries are pruned on every mint/verify.
    _MAX_USED = 10_000

    def __init__(
        self,
        *,
        secret: bytes | None = None,
        ttl_seconds: float = 120.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret or secrets.token_bytes(32)
        self._ttl = ttl_seconds
        self._clock = clock
        self._used: dict[str, float] = {}

    def mint(self, tool: str, args: dict[str, Any]) -> tuple[str, float]:
        """Return ``(token, expires_at)`` for this exact (tool, args)."""
        self._prune(self._clock())
        expires_at = self._clock() + self._ttl
        payload = {
            "tool": tool,
            "args": canonical_args(args),
            "exp": expires_at,
            "nonce": secrets.token_urlsafe(12),
        }
        body = _b64(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = _b64(hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{signature}", expires_at

    def verify(self, tool: str, args: dict[str, Any], token: str) -> None:
        """Raise :class:`ConsentError` unless ``token`` matches exactly."""
        try:
            body, signature = token.rsplit(".", 1)
        except ValueError as exc:
            raise ConsentError("malformed", _MALFORMED) from exc
        expected = _b64(
            hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ConsentError(
                "signature",
                "Consent token signature is invalid; call describe_tool again.",
            )
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ConsentError("malformed", _MALFORMED) from exc
        now = self._clock()
        if payload.get("tool") != tool:
            raise ConsentError(
                "tool",
                f"Consent token was minted for '{payload.get('tool')}', not '{tool}'.",
            )
        if payload.get("args") != canonical_args(args):
            raise ConsentError(
                "args",
                "Consent token does not match these arguments — the call changed after approval.",
            )
        if float(payload.get("exp", 0)) < now:
            raise ConsentError("expired", "Consent token expired; call describe_tool again.")
        nonce = str(payload.get("nonce", ""))
        if nonce in self._used:
            raise ConsentError("replayed", "Consent token was already used.")
        self._used[nonce] = float(payload["exp"])
        self._prune(now)
        while len(self._used) > self._MAX_USED:
            # Remove the oldest-inserted entry; it expires soonest/oldest.
            self._used.pop(next(iter(self._used)))

    def _prune(self, now: float) -> None:
        """Drop replay entries whose token has expired."""
        expired = [key for key, exp in self._used.items() if exp < now]
        for key in expired:
            self._used.pop(key, None)
