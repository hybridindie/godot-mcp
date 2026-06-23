"""Reusable bounded parameter types for tool inputs (issue #221).

Numeric tool params were unbounded, deferring all validation to the addon. These
``Annotated`` aliases attach Pydantic ``Field`` bounds so bad input is rejected
*before* the bridge round-trip and the bounds appear in the JSON schema the agent
sees. Bounds are deliberately generous — they reject absurd/typo values (a
negative timeout, a million samples), not legitimate use. Pass-through geometry
and identifiers (coordinates, node/port ids, device/axis indices) are left
unbounded on purpose: an artificial cap there would break valid Godot usage.

Each alias carries only the constraint; the per-tool default stays at the call
site, e.g. ``samples: Samples = DEFAULT_MONITOR_SAMPLES``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from mcp_server.defaults import DEFAULT_STRESS_MAX_ITERATIONS

# --- timeouts (caps stop a stalled call from hanging indefinitely) ----------
TimeoutSeconds = Annotated[float, Field(ge=0.1, le=3600.0)]
TimeoutMs = Annotated[int, Field(ge=1, le=600_000)]

# --- counts / limits on returned or generated items -------------------------
Samples = Annotated[int, Field(ge=1, le=1000)]
MaxResults = Annotated[int, Field(ge=1, le=10_000)]
ParticleAmount = Annotated[int, Field(ge=0, le=1_000_000)]
StressIterations = Annotated[int, Field(ge=1, le=DEFAULT_STRESS_MAX_ITERATIONS)]

# --- tree traversal depth; -1 means "unbounded" (whole tree) ----------------
MaxDepth = Annotated[int, Field(ge=-1, le=1000)]

# --- inter-event delays in milliseconds -------------------------------------
DelayMs = Annotated[int, Field(ge=0, le=600_000)]

# --- TileMap / TileSet identifiers ------------------------------------------
# source_id -1 is Godot's "empty/erase" sentinel; layer and alternative_tile are
# non-negative indices. No upper cap — these are open-ended Godot ids.
TileSourceId = Annotated[int, Field(ge=-1)]
TileSourceIdOpt = Annotated[int | None, Field(ge=-1)]
TileLayer = Annotated[int, Field(ge=0)]
TileLayerOpt = Annotated[int | None, Field(ge=0)]
TileAlternative = Annotated[int, Field(ge=0)]
