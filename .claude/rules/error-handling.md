---
paths:
  - "mcp_server/**/*.py"
  - "godot/addons/godot_mcp/**/*.gd"
---

# Error Handling & the JSON Envelope (Article IV)

Every message across the bridge is a versioned JSON envelope. Errors are structured data an agent can act on — never a stack trace, never silent.

## Envelopes (versioned from day one)

Command (server → addon):
```json
{ "id": "...", "command": "cmd_create_node", "params": { ... } }
```
Response (addon → server):
```json
{ "id": "...", "ok": true,  "result": { ... } }
{ "id": "...", "ok": false, "error": "RESOURCE_NOT_FOUND", "hint": "No node at 'Player/Gun'." }
```

MUST:
- Correlate every response to its command by `id`.
- On failure, set `ok: false` and return `error` (a stable code) plus a `hint` written for an agent to recover from.
- Precondition failures use the richer form so the agent knows what to satisfy:
```json
{ "ok": false, "error": "PRECONDITION_FAILED", "hint": "Open a scene before creating nodes.", "required": "active_scene" }
```

## Rules

MUST:
- Use stable, enumerated error codes (e.g. `PRECONDITION_FAILED`, `RESOURCE_NOT_FOUND`, `BRIDGE_DISCONNECTED`, `VALIDATION_ERROR`, `INTERNAL_ERROR`) — never ad-hoc strings.
- Catch errors at the bridge boundary on both sides and convert to an `ok: false` envelope. A GDScript runtime error or a Python exception must never escape as a raw trace to the client.
- Log with structured (JSON-friendly) records including the command `id`; include exception info on error-level logs.

MUST NOT:
- Swallow an error silently or return a partial `result` with an implicit failure.
- Log secrets, file contents, or full project paths beyond what the agent needs.
- Invent a new error code outside the enumerated set.

## Anti-patterns

- Returning `{ ok: true }` when the operation half-failed.
- A `hint` that restates the code instead of telling the agent what to do next.
- `print()` / `push_error()` as the only signal — the structured envelope is the contract.
