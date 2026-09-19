---
title: Bridge & transport
description: The WebSocket contract — connection direction, backoff, timeouts, and configuration.
---

# Bridge & transport

## Topology

The **server listens**, the **editor connects out** (#276). Both are
configurable via the same env var, `GODOT_MCP_BRIDGE_URL`
(default `ws://127.0.0.1:9080`) — never hard-coded in library code.

```mermaid
sequenceDiagram
    participant E as Godot addon
    participant S as MCP server (listener)
    Note over S: serve() binds :9080 — before, during, or after Godot launches
    E->>S: WebSocket connect (dials out)
    Note over E,S: transport up; server initiates everything from here
    S->>E: {id, command: "cmd_ping", params: {}}
    S-->>E: {id, ok: true, result: {pong: true}}
    Note over E,S: editor closes / restarts
    E-->>S: (connection lost)
    Note over E: exponential backoff ~500 ms → capped
    E->>S: reconnects
```

Why the editor dials:

- The editor is the party that comes and goes; the server is a headless
  service (often spawned per session by the MCP client, or a long-lived Docker
  service).
- Launch order never matters: the server may bind the port before Godot exists.
- Reconnection with exponential backoff (start ~500 ms, capped) lives on the
  addon side — the only party with enough knowledge to survive restarts.

## Framing & lifecycle

- **Framing:** one JSON object per WebSocket text message, UTF-8. No headers.
- **One active peer:** a new addon connection replaces the old one (a stale
  editor can't ghost the bridge).
- **No auth in v1**: localhost-only by design. For non-loopback HTTP binds the
  *server* (not the bridge) requires `GODOT_MCP_AUTH_TOKEN` (#226) — a
  fail-fast guard refuses to start otherwise.
- **`cmd_ping` → `{pong: true}`** is the health check, both directions.

## Timeouts, everywhere

A request that outlives its timeout resolves to a `TIMEOUT` envelope — it does
not hang the agent. Concretely:

| Timeout | Where | Value |
|---------|-------|-------|
| Bridge request | `Bridge.send(command, timeout=…)` | per-call; tool defaults vary (3–30 s) |
| Toolset enable's version fetch | `_fetch_godot_version` | 3 s, best-effort |
| HTTP transport | `GODOT_MCP_HTTP_*` via httpx client | tool-call bound (#422) |
| Readiness polls | `poll_ready(…, timeout_ms)` | per-tool (`timeout_ms` param) |
| Reconnect backoff | addon `mcp_bridge.gd` | ~500 ms start, capped |

A send with **no connected peer** resolves to `BRIDGE_DISCONNECTED`
immediately — it does not wait for an editor that isn't coming.

## Concurrency model

- **Id correlation is concurrency-safe**: many in-flight commands, each
  resolved to its own waiter keyed by `id`. No shared mutable state across
  requests.
- **Single-writer semantics**: one editor per bridge. A second connection
  *replaces* the first (documented; the server is single-user local by design).
- The server is **sessionless** by design (MCP `2026-07-28` shape): no
  per-session state, works on every transport, and `enable_toolset` writes a
  server-global set shared by all clients (see [gating](gating.md)).
- No blocking sync I/O inside async handlers; no import-time sockets.

## Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `GODOT_MCP_BRIDGE_URL` | `ws://127.0.0.1:9080` | bridge listen/connect URL (both sides) |
| `GODOT_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `GODOT_MCP_HTTP_HOST` / `_PORT` | `127.0.0.1:9090` | HTTP bind |
| `GODOT_MCP_AUTH_TOKEN` | unset | Bearer token — **required** for non-loopback HTTP binds (#226) |
| `GODOT_MCP_PROJECT_DIR` | unset | explicit project dir (else the connected editor's) |

The full table lives in [env-vars](../reference/env-vars.md).

## Testing the seam

The bridge is the seam most worth testing, so it gets two layers:

1. **Fake addon connection** (`tests/fakes.py`): an in-memory transport that
   validates real envelope shapes, correlating `id`s, and canned responses —
   the entire contract suite runs with no sockets and no editor.
2. **Live e2e** (`tests/integration/test_*_e2e.py`): a real editor on a
   self-hosted runner; ephemeral per-run bridge ports (#444) so concurrent
   jobs can't contend; the addon's reconnect behavior is exercised by
   dedicated tests (#276).

The bridge inversion was itself landed with a red-first e2e: the old
"addon-hosts" topology hung on every server restart; the "server-listens"
topology survives any restart order.