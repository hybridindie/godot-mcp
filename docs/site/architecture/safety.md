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
| `mutating` | Reversible/additive change (UndoRedo) | `dry_run: bool = False` | `create_node`, `set_node_property`, `attach_script`, `set_resource_property` |
| `destructive` | Removes/overwrites existing data, or an irreversible disk/project write | `dry_run` **and** `confirm: bool = True` | `delete_node`, `reload_scene`, `close_scene`, `remove_audio_bus`, `delete_resource_file`, `create_resource`, `set_setting`, `cross_scene_set_property`, `register_autoload`/`unregister_autoload`, `disconnect_signal` |
| `runtime` | Controls/side-effects game execution | varies | `play_scene`, `run_and_capture`, `export_project`, `monitor_property`, `stop_recording`, `rescan_filesystem`, `evaluate_expression` |

### Classification rule

The class follows the effect, not the verb (issue #638):

- **Reversible, additive editor edit** (UndoRedo restores it) → `mutating`.
- **Removes/overwrites existing data, or writes disk/project state the undo
  stack does not cover** → `destructive`. That includes resource/scene file
  writes (`create_resource`, `cross_scene_set_property`), `ProjectSettings`
  persistence (`set_setting`, `register_autoload`/`unregister_autoload`), and
  breaking a signal connection (`disconnect_signal`) — even where the editor
  happens to undo-track the step, the agent must opt in.
- **Side-effecting observation** (starts/stops a recorder, starts sampling,
  triggers a reimport) → `runtime`, not `read_only`.

A contract test (`tests/contract/test_safety_classification.py`) pins the class
of every tool the audit touched, so a misclassification fails CI.

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

**What `confirm` does and does not protect against.** `confirm` is an *accident
guard*: the agent sets it itself, so it stops a tool being called by reflex
without deliberation — it is **not** human oversight. Real human-in-the-loop
oversight is the opt-in **approval gate** (`GODOT_MCP_APPROVAL_WEBHOOK`, or the
elicitation guard with `GODOT_MCP_APPROVAL_REQUIRE`): `mutating`/`destructive`
calls — and `runtime` tools flagged `writes_disk`/`executes_code`
(`export_project`, `evaluate_expression`) — are routed to it. With a webhook
configured, an **unreachable** webhook now fails **closed** (denies) by default
(issue #638); set `GODOT_MCP_APPROVAL_FAIL_OPEN=true` to opt into fail-open.

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
layer that gates *who can connect at all*. Listener hardening (#636) is the
third: the bridge refuses browser-`Origin` WebSocket handshakes and the HTTP
transport's Host/Origin guard is on by default, so a visited web page (WebSocket
same-origin exemption, DNS rebinding) can't reach the code-executing tools —
while a *local* process still only needs the bridge/token, since loopback is
single-user by design.

### Batch tools don't bypass the gates

A macro/batch tool is a convenience, not a privilege escalation. `run_commands`
resolves each sub-command back to the tool that backs it and enforces that
tool's policy per entry (#634): a sub-command from a disabled toolset is
refused, a destructive entry needs `confirm=True`, params go through the path
preflight, and an unknown `cmd_*` is refused — a batch containing a delete is
presented to the approval gate as `destructive`, not as the outer tool's
`mutating` class.

### Path containment

Every file-path parameter is a `ResPath` (a contained `res://` path) — the
server rejects a missing scheme, an absolute filesystem path, or a `res://../`
escape at the schema boundary, before the bridge round-trip (#637). The addon's
own `begins_with("res://")` check is not trusted for this. `run_commands`
sub-commands, which bypass the argument schema, are re-checked by the same
preflight predicate. Node paths (`Player/Gun`) are not `res://` paths and are
exempt. `export_project`'s `output_path` is confined to the project dir: a target
outside it is refused unless `confirm=True`.

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