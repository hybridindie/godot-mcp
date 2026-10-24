---
type: index
title: "Why & how it works"
description: "The problem Godot Editor MCP solves, why it's built this way, and the ideas every other page assumes."
created: 2026-09-19
updated: 2026-10-18
---

# Why & how it works

Two minutes here and the rest of the docs will click.

## Naming: Godot Editor MCP

**Godot Editor MCP** is the product name, chosen because the **editor is the surface**:
every action lands on the live Godot editor through the addon, not on files behind its
back.

The identifiers are deliberately stable and slightly different:

| Thing | Value | Why |
|-------|-------|-----|
| Product | **Godot Editor MCP** | human-facing name |
| Repository | `godot-mcp` | existing URLs and history |
| MCP server ID | `godot-mcp` | wire compatibility with existing clients |
| Package / CLI | `godot-editor-mcp` | published PyPI name |
| Addon | **Godot Editor MCP - Addon** | Godot Asset Store name |
| Tools | `godot_<toolset>_<action>` | the prefix is the toolset gate |

If a page says "the server" it means the Python MCP server; "the addon" means the
GDScript editor plugin. Both together are Godot Editor MCP.

## The problem

An AI agent can already edit Godot files on disk — but it edits **blind**:

- it can't *see* the live scene (instanced scenes, `owner` relationships, the open tab, the selection, unsaved edits);
- it can't *run* anything, so "does this work?" is unanswerable without a human pressing play;
- its file writes race the editor's importer, so its next check can read a stale class cache;
- a mistake has no undo unless the editor's own stack was involved.

Godot Editor MCP closes that gap: the agent talks to the **live editor** over MCP, so every action lands on the project you're actually looking at — with undo, verification, and honest reporting.

## Why it's built this way (the short version)

- **Editor-first, not file-first.** The editor owns state the disk doesn't — unsaved changes, `owner`, editable-instance flags, the selection, the importer cache. Every mutation goes through the editor's own APIs (`EditorUndoRedoManager`, `EditorInterface`, `ProjectSettings`), so *your* undo stack covers the agent's actions and the editor's own rules apply.
- **The server listens; the editor connects out.** The editor is the app that comes and goes, so it's the one that dials and reconnects (with backoff). The server can start before Godot, before the agent's first call, or in Docker — launch order never matters. The direction of commands is unchanged: the server still initiates every one.
- **Safety lives in the server, not the addon.** The addon only executes; it never decides whether an action is allowed. Safety classes, previews, `confirm` gates, and preconditions all live in `mcp_server/safety.py`, so a misbehaving addon can't bypass the confirm gate.
- **Honest results over optimistic ones.** A result that *reads* like success but isn't is the worst failure mode for an agent with no human watching. So nothing ever says "done" without saying what happened to disk (see the honesty fields below).
- **Game-agnostic by design.** No game vocabulary ships here. A game-specific project layers its own tools and prompts on top; anything that only makes sense for one game belongs there, not here.

## The ideas every page assumes

### 1. The toolset (the gating unit)

Every tool carries **exactly one category tag**. `core` (diagnostics and toolset
management) is always on; everything else ships **gated off**. The agent switches
one on with `godot_enable_toolset("scene_edit")`, which updates a server-global
enabled set and announces the change (`notifications/tools/list_changed`, plus a
`subscriptions/listen` stream on the `2026-07-28` protocol). Because many clients
ignore the notification, the enable result also carries the enabled tools' names
and input schemas, so even a client that never refreshes can call them.

Why gate at all? 201 tools in the context window degrade tool-selection and burn
tokens. The default surface (`core` + `inspection` — 29 tools) is enough to orient
and inspect; the agent pulls in `scene_edit` only when it means to edit.
`godot_list_toolsets()` is always authoritative.

A few toolsets are version-gated (`scene_edit`, `input_map`, `tilemap`,
`scene_3d` need Godot 4.4+); enabling one on an older editor returns a structured
`PRECONDITION_FAILED … [required=godot_version]`.

### 2. The safety class

Every tool is one of:

| Class | Meaning | Extra params |
|-------|---------|--------------|
| `read_only` | Never mutates | none |
| `mutating` | Reversible editor change (UndoRedo) | `dry_run: bool = False` |
| `destructive` | Deletes/overwrites; maybe irreversible | `dry_run` **and** `confirm: bool = True` |
| `runtime` | Controls game execution | varies |

`dry_run=True` runs the checks and returns what *would* happen — nothing is sent.
`confirm=True` is required for destructive tools; without it the tool returns
`PRECONDITION_FAILED … [required=confirm]`. `godot_undo` covers every
UndoRedo-wrapped change (batches above 20 nodes bypass the stack and say so via
`undoable: false`).

### 3. The envelope (and why errors look like this)

```jsonc
// server → addon (command)
{ "id": "42", "command": "cmd_create_node", "params": { "parent_path": ".", "node_type": "Node2D", "name": "Player" } }
// addon → server (response)
{ "id": "42", "ok": true, "result": { "node_path": "Player", "created": true } }
```

Failures never cross as stack traces:

```jsonc
{ "id": "42", "ok": false, "error": "PRECONDITION_FAILED", "hint": "Open a scene before creating nodes.", "required": "active_scene" }
```

`error` is from a fixed enum; `hint` tells the agent what to do next; `required`
names the precondition to satisfy. The server shapes these into FastMCP
`ToolError`s, so the agent sees the same structured failure on every transport.

Almost every response is JSON like the above. The one exception is a screenshot: the
same round-trip returns PNG bytes that the server hands the model as an image, so the
agent can *look at* the editor viewport or the running game — see
[Seeing the scene](guides-playtest-debug.md#see-the-scene-screenshots).

### 4. Naming: `godot_<toolset>_<action>`

The exposed name is the gating toolset made visible: `create_node` in the
`scene_edit` toolset is `godot_scene_edit_create_node`. The prefix *is* the gate —
an agent can read the name and know what it must enable. Always-on `core`/meta
tools are just `godot_<action>` (`godot_health_check`, `godot_enable_toolset`). The
mapping is applied centrally and enforced by a contract test.

### 5. Honesty fields

Results carry structured self-reporting that reads as ground truth:

| Field | On | Meaning when it matters |
|-------|----|-------------------------|
| `persisted` + `reason` + `hint` | most mutations | whether a scene save will keep the change; `instanced_child_not_editable`, `node_not_owned`, `embedded_in_other_resource`, `group_from_base_scene` are the reason tokens |
| `undoable` | `batch_set_property` | `false` above 20 nodes — undo will **not** revert the batch |
| `aborted_at`, `skipped_count`, `hint` | `run_commands` | which sub-command stopped the batch and how many never ran |
| `may_have_applied` | any mutating/`destructive` tool, on `TIMEOUT` | the timed-out mutation may still run on the editor (it drains commands serially) — re-read state before retrying, don't double-apply (#644) |
| `rescan_pending` | `get_parse_errors` | the editor's rescan hadn't flushed; a fresh-class_name error may be stale cache |
| `reason` (readiness) | poll-based tools | why the tool is still pending (`capture_pending`, `scan_in_flight`, …) |
| `scanning` | `asset_import_get_status`, `rescan_filesystem` | the editor's filesystem scan is in flight |

### 6. Contract versioning

The **contract** is the stable public surface a client builds against — tool names and
parameters, result fields, value shapes, the envelope, errors, and safety semantics.
`godot_get_server_info` carries `contract_version` (a breaking-change counter, currently
**1**) and `min_compatible_contract`. A client is compatible when
`min ≤ client ≤ contract`. Additive changes (new tools, optional fields) never bump it;
removals and renames do. The CalVer build version (`2026.10.20.1`) moves every release and
is *not* the compatibility signal.

Full explainer: **[The compatibility contract](reference-contract.md)**.

---

Deep dive next: **[Under the hood](architecture/index.md)** — the four-layer chain,
the bridge, and the full contract.
