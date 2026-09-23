---
type: index
title: "The safety model"
description: "Safety classes, preconditions, dry_run/confirm, and why safety lives in the server."
created: 2026-09-19
updated: 2026-09-23
---

# The safety model

Every tool carries a **safety class** that determines its risk and required
parameters. The class is metadata on the tool (`meta.safety_class`), and every
class change is pinned by contract tests.

## The classes

| Class | Risk | Extra params | Examples |
|-------|------|--------------|----------|
| `read_only` | None | none | `get_scene_tree`, `scripts_read`, `shader_validate` |
| `mutating` | Reversible change (UndoRedo) | `dry_run: bool = False` | `create_node`, `set_node_property`, `attach_script` |
| `destructive` | Deletes/overwrites; maybe irreversible | `dry_run` **and** `confirm: bool = True` | `delete_node`, `reload_scene`, `close_scene`, `remove_audio_bus`, `delete_resource_file` |
| `runtime` | Controls game execution | varies | `play_scene`, `run_and_capture`, `export_project` |

Two knobs do the work:

- **`dry_run=True`** runs preconditions and returns what *would* happen. For
  most mutations the preview carries the same persistence verdict the real run
  will stamp — the tool sends the read-only `cmd_node_persistence` probe, and
  the addon answers with the same rule the real handler applies (preview and
  real run always agree).
- **`confirm=True`** is required for destructive tools. Without it:
  `PRECONDITION_FAILED: This call discards unsaved changes. Set confirm=True
  to proceed. [required=confirm]`. The server enforces this; the addon honors
  the flag defensively too.

## Preconditions

Checked **before** any side effect, and failing with a structured error —
never a Python exception:

| Precondition | Required token | Recovered by |
|--------------|----------------|--------------|
| `require_bridge_connected` | `bridge_connected` | open Godot + enable the addon |
| `require_active_scene` | `active_scene` | `open_scene` / `create_scene` |
| `require_node_exists(path)` | — (`RESOURCE_NOT_FOUND`) | `get_scene_tree` to find real paths |
| `require_godot_binary` | `godot_binary` | install Godot / set `GODOT_BIN` |
| toolset version gate | `godot_version` | upgrade the editor |
| game-not-break gate (input sim) | `game_not_breaked` | `godot_debugger_continue_execution` |

## Where safety lives, and why

All safety logic lives in `mcp_server/safety.py` — **never** in the addon.

Reasoning:

- The addon is the only layer that touches Godot, but it is the *least*
  trustworthy layer: it runs inside the editor process, next to user code, and
  is version-coupled to Godot. Keeping it a dumb, auditable executor means a
  corrupted addon cannot bypass the `confirm` gate.
- The server owns the classes/params once, and the same rules apply across
  stdio, HTTP, and Docker — a safety decision made in GDScript would only
  protect Godot clients.
- The split makes the surface reviewable: `safety.py` (one file) is where an
  auditor reads the whole permission model.

The classes apply **in every transport mode**; transport-level auth (the
`GODOT_MCP_AUTH_TOKEN` gate on non-loopback HTTP binds) is a second, separate
layer that gates *who can connect at all*.

## Honesty as safety

The most dangerous failure mode is a result that reads like success but isn't.
The persistence system exists for exactly that:

- Structural edits stamp `persisted` with a `reason` +
  actionable `hint` (see [persistence](persistence.md)).
- Batch sets above 20 nodes report `undoable: false`.
- `run_commands` reports `aborted_at` / `skipped_count` / an unsaved-scene
  hint.
- Parse checks report `rescan_pending` when they raced an importer scan.
- Timeout kills are distinguished from crashes.

These fields are contract-pinned; skills and evals treat them as ground truth.
The rule of thumb in the codebase: **a result never reads as success when the
effect half-failed.**

## UndoRedo

Every create/rename/delete/set operation registers with
`EditorUndoRedoManager` — the human's undo stack covers agent actions. The
documented exceptions report themselves: batch sets above 20 nodes bypass the
stack for performance (`undoable: false` in the result), and
`set_setting`/file-only resource authors are not undo-tracked (their contracts
say so).