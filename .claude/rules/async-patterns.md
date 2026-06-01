---
paths:
  - "mcp_server/**/*.py"
---

# Async-First & the Bridge Transport (Article V)

FastMCP runs an async server. The WebSocket bridge is the one place latency and failure live — handle both explicitly.

## MUST

- All `@mcp.tool()` / `@mcp.resource()` handlers are `async def`. Never call `asyncio.run()` inside the server — the runtime owns the loop.
- No blocking synchronous I/O inside `async def` (wrap unavoidable sync calls in an executor, with a comment).
- The bridge client sets an explicit timeout on every request; a request that outlives its timeout resolves to a `TIMEOUT` envelope (see [[error-handling]]), it does not hang.
- Reconnect on bridge failure with exponential backoff (start ~200ms, jitter, capped). A `ping`→`pong` health check confirms liveness.
- Request/response correlation by `id` is concurrency-safe — many in-flight commands, each resolved to its own waiter. No shared mutable state across requests.
- Pydantic-typed boundaries in and out (see [[mcp-tools]]).

## SHOULD

- Injectable clock for deterministic tests of timeout/backoff.
- Document concurrency assumptions when a handler is only safe under single-writer (single editor) semantics.

## Anti-patterns

- A synchronous WebSocket client inside async code.
- Firing a bridge command without awaiting its correlated response (orphaned `id`).
- Creating the event loop or connecting the socket at import time.
- Module-level dict/list holding per-request state.
- No timeout on a bridge call — a stalled editor then hangs the agent.
