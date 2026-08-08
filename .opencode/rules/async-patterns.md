---
paths:
  - "mcp_server/**/*.py"
---

# Async-First & the Bridge Transport (Article V)

FastMCP runs an async server. The WebSocket bridge is the one place latency and failure live — handle both explicitly.

## MUST

- All `@mcp.tool()` / `@mcp.resource()` handlers are `async def`. Never call `asyncio.run()` inside the server — the runtime owns the loop.
- No blocking synchronous I/O inside `async def` (wrap unavoidable sync calls in an executor, with a comment).
- The bridge sets an explicit timeout on every request; a request that outlives its timeout resolves to a `TIMEOUT` envelope (see [[error-handling]]), it does not hang.
- The server **listens** for the editor and accepts one active peer (a new connection replaces the old); reconnection lives on the **addon** side, which dials out and retries with exponential backoff (#276). A `cmd_ping`→`{pong}` exchange confirms liveness. A send with no connected peer resolves to a `BRIDGE_DISCONNECTED` envelope, it does not hang.
- Request/response correlation by `id` is concurrency-safe — many in-flight commands, each resolved to its own waiter. No shared mutable state across requests.
- Pydantic-typed boundaries in and out (see [[mcp-tools]]).

## SHOULD

- Injectable clock for deterministic tests of timeout/backoff.
- Document concurrency assumptions when a handler is only safe under single-writer (single editor) semantics.

## Sessionless-era compatibility (FastMCP 4.0)

The server is stateless by design — no `ctx.elicit()`, `ctx.set_state`, or `Middleware.on_initialize` — so it works on the modern sessionless `2026-07-28` protocol (which `fastmcp.Client` negotiates by default in 4.0) without porting. Do not add features that depend on per-session state or server-initiated requests; if a future tool needs a back-channel to the client, use the guard pattern (return an `InputRequiredResult` describing what the tool needs, and the client calls again with the answer) rather than `ctx.elicit()`, which raises on the modern protocol. `ctx.info` / `ctx.report_progress` are safe — they ride the response stream as notifications, not requests — but guard them with `safe_info` / `safe_progress` (`mcp_server/tools/_progress.py`) so they no-op in the detached task session (`task=True`), where `ctx.session` is `None`.

## Anti-patterns

- A synchronous WebSocket client inside async code.
- Firing a bridge command without awaiting its correlated response (orphaned `id`).
- Creating the event loop or connecting the socket at import time.
- Module-level dict/list holding per-request state.
- No timeout on a bridge call — a stalled editor then hangs the agent.
