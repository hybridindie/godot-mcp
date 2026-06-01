"""Bridge configuration (issue #3).

The bridge URL and request timeout are configuration, never hard-coded in
library code (see .claude/rules/architecture.md). Defaults are localhost-only
with no auth, per the v1 design.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

DEFAULT_BRIDGE_URL = "ws://localhost:9080"
DEFAULT_REQUEST_TIMEOUT = 10.0

# Environment override for the bridge URL.
BRIDGE_URL_ENV = "GODOT_MCP_BRIDGE_URL"


class BridgeConfig(BaseModel):
    """Connection settings for the Godot addon bridge."""

    url: str = DEFAULT_BRIDGE_URL
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Build config from the environment, falling back to localhost defaults."""
        return cls(url=os.environ.get(BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL))
