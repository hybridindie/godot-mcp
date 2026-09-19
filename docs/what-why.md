---
title: What & why
description: The problems godot-mcp solves, and why it is built the way it is.
---

# What & why

## The problem it solves

An LLM agent can already edit Godot files on disk — but it edits **blind**:

- It cannot *see* the live scene: no tree, no selection, no properties as the
  editor holds them (instanced scenes, owner state, editor-only metadata).
- It cannot *run* anything. "Does this work?" is unanswerable without a human
  pressing play.
- File edits race the editor's importer: a `.gd` written on disk may parse in
  the agent's head but the editor hasn't rescanned, so the agent's next check
  reads a stale class cache.
- A destructive mistake (a deleted scene, an overwritten script) has no undo —
  unless the editor's undo stack was involved.

godot-mcp closes that gap: the agent talks to the **live editor** over MCP, so
every action happens against the project the developer is actually looking at,
with undo, verification, and honest reporting.

## The reasoning behind the design

### Editor-first, not file-first

Blind file editing *looks* simpler — no bridge, no addon — but the editor owns
authoritative state the disk does not: unsaved changes, `owner` relationships,
editable-instance flags, open tabs, the selection, and the importer cache.
File-first agents drift from the editor's view and "fix" things that are
already correct (or break things that were correct).

So godot-mcp is **editor-first**: every mutation goes through the editor's own
APIs (`EditorUndoRedoManager`, `EditorInterface`, `ProjectSettings`), which
means the human's undo stack covers agent actions, the editor's own validation
rules apply, and the agent sees the same scene the human sees.

### The bridge: server listens, editor connects out

The obvious topology is "addon hosts a WebSocket server, MCP server connects."
It was built that way first — then inverted (#276). Reasoning:

- The **editor is the party that comes and goes.** It is a desktop app the
  human opens and closes; the MCP server is a headless service the agent spawns.
  A client that dials out and reconnects with backoff is the robust party.
- The spawned server cannot know when the editor will appear. A **listener**
  can start before Godot, before the agent's first tool call, or in Docker —
  launch order never matters.
- Reconnection is owned by whichever side has the least information about the
  other's lifetime. The addon's backoff loop is the only thing that needs to
  survive a server restart.

The request/response *direction* is unchanged: the server still initiates every
command (`{id, command, params}`), the addon responds (`{id, ok, result}`).
Only who dials changed — which is the only part that needed to.

### One JSON envelope, versioned from day one

Every message across the bridge is `{id, command, params}` / `{id, ok, result,
error, hint}`. The `id` correlates request and response (many in-flight
commands, each resolved to its own waiter). `error` is a stable enumerated code
(`PRECONDITION_FAILED`, `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR`,
`BRIDGE_DISCONNECTED`, `TIMEOUT`, `INTERNAL_ERROR`), never a stack trace, and
precondition failures carry a `required` field the agent can act on. The
envelope has been shape-stable since the first PR, which is why a client built
against contract **1** still works against a 2026 build.

### Safety lives in the server, not the addon

The addon is the only layer that touches Godot, but it never decides *whether*
an action is allowed. Safety classes, `dry_run` previews, `confirm` gates, and
preconditions live in `mcp_server/safety.py`. This keeps the addon a dumb,
auditable executor — a corrupted addon cannot bypass the confirm gate — and
lets the same safety apply over stdio, HTTP, and Docker alike.

### Honest results over optimistic ones

The most dangerous failure mode for an agent with no human in the loop is not
an error — it is a result that *reads* like success but isn't. So the surface
never says "done" without saying what happened to disk:

- Every mutation result carries a **persistence verdict** (`persisted`, with a
  stable `reason` + actionable `hint` when the save will drop the change).
- Batches above the undo threshold say `undoable: false`.
- Early-stopped batches report `aborted_at` / `skipped_count`.
- Parse checks racing an importer scan return `rescan_pending: true`.
- Timeout kills are distinguished from crashes (`exit_code=None` is not a
  non-zero exit).

These are not decorations; agents that ignore them double-write, undo the
wrong things, or "fix" correct code. The skills and the eval harness treat
them as ground truth.

### Game-agnostic by constitution

godot-mcp ships **no** game vocabulary. No towers, no waves, no enemies. A
consumer project (e.g. [godot-agents](https://github.com/hybridindie/godot-agents))
layers its own domain models on top. Anything that only makes sense for one
game belongs in that game's project, not here — this keeps the server
reusable for any genre and keeps the surface small.

## What it is not

- **Not a headless build server.** The editor is a live participant; the goal
  is human + agent working in the same editor, not CI automation (though
  headless runs exist for verification).
- **Not a game framework.** There are no gameplay tools and no game models.
- **Not a generic MCP server for anything.** The surface is Godot-shaped by
  design; that specificity is what makes 184 tools useful instead of 184 ways
  to say "read a file".

---

*Deep-dive next: [the four-layer architecture](architecture/index.md), or the
[transport contract](architecture/bridge.md).*