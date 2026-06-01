# Architecture: the WebSocket bridge contract

This document is the contract for the seam between the two halves of godot-mcp. It is
authoritative for the **transport** and the **JSON envelope**; the tool/resource/prompt
surface is specified in [`tool-contracts.md`](tool-contracts.md). The grounding rules in
[`../.claude/rules/`](../.claude/rules/) govern *how* code on each side is written.

> Status: the bridge is implemented (issue #3). Server side: `mcp_server/bridge.py`
> (async client, `id` correlation, timeout, backoff reconnect) over the envelope models
> in `mcp_server/models/envelope.py`. Addon side: `mcp_bridge.gd` (`TCPServer` +
> `WebSocketPeer`) routing through `command_router.gd`. `ping` → `{pong: true}` is the
> health check. Higher-level `cmd_*` handlers and MCP tools build on this contract.

## The four-layer transport chain

Every agent action crosses all four layers:

```
AI client (Claude Code / OpenCode / any stdio MCP client)
    │  stdio (MCP protocol)
FastMCP server  (Python, mcp_server/)
    │  WebSocket — localhost, default ws://localhost:9080
Godot EditorPlugin  (GDScript, godot/addons/godot_mcp/)
    │  Godot Editor API
Live Godot project
```

- **MCP server** (`mcp_server/`) is the WebSocket **client** and the AI-facing stdio
  server. It owns all safety, permission, and precondition logic and the Pydantic domain
  models. It holds no Godot logic.
- **Godot addon** (`godot/addons/godot_mcp/`) is the WebSocket **server** (a `TCPServer`
  upgraded to `WebSocketPeer`). It is the only code that touches the Godot Editor API.

Direction of control: the **server initiates** every request; the addon responds. The
addon never pushes unsolicited commands. (Editor-event streaming, if added later, will be
a separate, explicitly-versioned channel.)

## Transport

- **URL:** `ws://localhost:9080` by default. Configurable on both sides; never hard-coded
  in library code. localhost-only, **no auth in v1**.
- **Framing:** one JSON object per WebSocket text message. UTF-8.
- **Connection lifecycle:** the addon listens; the server connects. On bridge failure the
  server reconnects with **exponential backoff** (start ~200 ms, jittered, capped). A
  `ping` → `pong` exchange is the liveness health check.
- **Concurrency:** many requests may be in flight; each response is matched to its request
  by `id`. Correlation is concurrency-safe — no shared mutable per-request state. The
  editor is a single writer, so mutating commands are effectively serialized by the addon.

## The JSON envelope (versioned from day one)

### Command — server → addon

```json
{ "id": "uuid-or-monotonic-string", "command": "cmd_create_node", "params": { "...": "..." } }
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique per request; the response echoes it. |
| `command` | string | An addon handler name, always `cmd_<verb>_<noun>`. |
| `params` | object | Command arguments. Godot types are JSON-coerced (see below). |

### Response — addon → server

Success:

```json
{ "id": "…", "ok": true, "result": { "...": "..." } }
```

Failure:

```json
{ "id": "…", "ok": false, "error": "RESOURCE_NOT_FOUND", "hint": "No node at 'Player/Gun'." }
```

Precondition failure (richer form, so the agent knows what to satisfy):

```json
{ "id": "…", "ok": false, "error": "PRECONDITION_FAILED",
  "hint": "Open a scene before creating nodes.", "required": "active_scene" }
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Echoes the command `id`. |
| `ok` | bool | `true` ⇒ `result` present; `false` ⇒ `error` + `hint` present. |
| `result` | object | Present only when `ok: true`. JSON-safe types only. |
| `error` | string | Present only when `ok: false`. A **stable, enumerated** code. |
| `hint` | string | Present only when `ok: false`. Actionable for an agent with no human in the loop. |
| `required` | string | Only on `PRECONDITION_FAILED`: the precondition to satisfy. |

### Rules

- **Correlate by `id`.** A response with an unknown or missing `id` is dropped and logged.
- **Never leak a trace.** A GDScript runtime error or a Python exception is caught at the
  bridge boundary on its own side and converted to an `ok: false` envelope.
- **Stable error codes only**, drawn from the enumerated set below — never ad-hoc strings.
- **A timed-out request resolves to a `TIMEOUT` envelope**; it never hangs the agent.
- **No partial success.** Half-completed work returns `ok: false`, not `ok: true` with a
  truncated `result`.

### Enumerated error codes (v1)

| Code | Meaning |
|------|---------|
| `PRECONDITION_FAILED` | A required condition (e.g. `active_scene`) is not met; see `required`. |
| `RESOURCE_NOT_FOUND` | A referenced node/scene/resource does not exist. |
| `VALIDATION_ERROR` | Params failed schema/type validation. |
| `BRIDGE_DISCONNECTED` | The addon is not reachable. |
| `TIMEOUT` | No response within the request's timeout. |
| `INTERNAL_ERROR` | An unexpected failure on either side (still structured, never a trace). |

This table is the source of truth for the error enum; extend it here (and in the
contract tests) before adding a new code.

## Type coercion

Godot types cross the bridge as JSON-safe forms, coerced on the addon side in the
dedicated `type_coerce.gd` helper (`MCPTypeCoerce`), never inline. The read direction
(Godot → JSON) landed in issue #5; the write direction (`from_json`, using each property's
declared type to reconstruct the Godot value) lands with the mutation tools in issue #6.

| Godot type | JSON shape |
|------------|------------|
| `Vector2` / `Vector2i` | `{ "x": float, "y": float }` |
| `Vector3` / `Vector3i` | `{ "x": float, "y": float, "z": float }` |
| `Color` | `{ "r": float, "g": float, "b": float, "a": float }` |
| `Rect2` / `Rect2i` | `{ "position": {x,y}, "size": {x,y} }` |
| `NodePath` / `StringName` | string |
| `Resource` | its `resource_path` (else the class name) |
| `Array` / packed arrays / `Dictionary` | coerced element-wise |
| `null`, `bool`, `int`, `float`, `String` | passed through unchanged |

Scene trees serialize to `{ name, type, script, children }` and honor a `max_depth`
parameter (`-1` = unlimited, `0` = the node with no children). Node detail serializes to
`{ node_path, type, script, properties, children }` (see [`tool-contracts.md`](tool-contracts.md)).

## Runtime execution (issue #13)

The `run_and_capture` tool is the one place the server launches a **Godot process
directly** (`godot --headless --path <project> [scene]`) rather than going through
the bridge. This is a deliberate, reasoned exception to "the bridge is the only path
to Godot" (Article II): running the game for verification is *process execution*,
not *editor control*, and Godot exposes no public GDScript API to read the editor's
Output/error log, so the addon cannot capture a separate game process's stdio. The
bridge stays the only path for editor control; the runner is isolated in
`mcp_server/runtime.py` with an injected subprocess so it stays testable. Interactive
in-editor play/stop (via `EditorInterface.play_*`) is a possible later addition.

## Health check

`ping` → `pong` is the canonical liveness probe and the first contract test (issue #3).
The server's `health_check` tool (issue #4) reports server version plus bridge connection
state, built on this probe.
