---
paths:
  - "mcp_server/**/*.py"
---

# Architecture: Library-First & the Addon/Server Boundary (Articles I & II)

The system is two halves joined by one seam. Keep the seam clean; keep logic out of the handlers.

```
AI client ──stdio──> FastMCP server (Python) ──WebSocket──> Godot addon (GDScript) ──> live project
```

## Library-First (Article I)

MUST:
- Tool/resource/prompt handlers in `mcp_server/{tools,resources,prompts}/` are **delegation only** — validate args, call a service or the bridge, return a typed model. Zero domain logic in `@mcp.tool()` / `@mcp.resource()` / `@mcp.prompt()` bodies.
- Reusable logic lives in dedicated modules: the WebSocket transport in `mcp_server/bridge.py`, safety/precondition logic in `mcp_server/safety.py`, domain types in `mcp_server/models/`.
- No side effects at import time (no socket connect, no `mcp.run()` outside `if __name__ == "__main__"`).

SHOULD:
- Functions composition-focused and under ~40 lines.
- Split a module once it spans two unrelated concerns.

ANTI-PATTERNS (BLOCKING):
- Domain branching inside a tool handler.
- A handler reaching into Godot semantics directly instead of sending a bridge command.
- Module-level mutable state holding per-request data (the server is long-lived).

## Service Isolation (Article II)

MUST:
- The bridge client is the **only** way Python talks to Godot. No Godot/editor knowledge leaks into tool handlers or models.
- The Python layer owns **all** safety, permission, and precondition logic (see [[mcp-tools]]); the addon owns **all** Godot Editor API calls (see [[addon]]). Neither crosses into the other.
- Services and the bridge take injected clients (socket, clock, config) — no global singletons.
- Return typed Pydantic models, never `dict[str, Any]`, across module boundaries.

ANTI-PATTERNS:
- A second code path to Godot that bypasses the bridge envelope.
- Hard-coded bridge URL/port inside library code (read from config; default `ws://localhost:9080`).
- `datetime.now()` / ambient time without injection.
