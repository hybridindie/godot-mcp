---
type: index
title: "Core concepts"
description: "Toolsets, safety classes, the envelope, tool naming, and honesty fields — the vocabulary the rest of the docs assume."
created: 2026-09-19
updated: 2026-09-19
---

# Core concepts

These are the terms every other page uses. Five ideas cover the whole system.

## 1. The toolset (gating unit)

Every tool carries **exactly one category tag**. `core` (diagnostics, toolset
management) is always on; everything else ships **gated off**. The agent turns
a toolset on with `godot_enable_toolset("scene_edit")`, which writes into a
server-global enabled set and (since 2026.09.17) emits
`notifications/tools/list_changed` so clients refresh their cached registry.

Why gate at all? 186 tools in the context window degrade tool-selection and
burn tokens. The default surface (`core` + `inspection` — 18 tools) is enough
to orient and inspect; the agent pulls in `scene_edit` only when it means to
edit. `godot_list_toolsets()` is always authoritative.

Some toolsets are version-gated: `scene_edit`, `input_map`, `tilemap`,
`scene_3d` require Godot 4.4+, because they lean on editor APIs validated
there. Enabling one on an older editor returns a structured
`PRECONDITION_FAILED … [required=godot_version]`.

## 2. The safety class

Every tool is one of:

| Class | Meaning | Extra params |
|-------|---------|--------------|
| `read_only` | Never mutates | none |
| `mutating` | Reversible editor change (UndoRedo) | `dry_run: bool = False` |
| `destructive` | Deletes/overwrites; maybe irreversible | `dry_run` **and** `confirm: bool = True` |
| `runtime` | Controls game execution | varies |

`dry_run=True` runs preconditions and returns what *would* happen — nothing is
sent. `confirm=True` is required for destructive tools; without it the tool
returns `PRECONDITION_FAILED … [required=confirm]`. `godot_undo` covers every
UndoRedo-wrapped mutation (batch sets above 20 nodes bypass the stack and say
so via `undoable: false`).

## 3. The envelope (and why errors look like this)

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
`ToolError`s, so the agent sees the same structured failure regardless of
transport.

## 4. Naming: `godot_<toolset>_<action>`

The exposed name is the gating toolset made visible: `create_node` in the
`scene_edit` toolset is `godot_scene_edit_create_node`. The prefix *is* the
gate — an agent can read the name and know what it must enable. Always-on
`core`/meta tools are just `godot_<action>` (`godot_health_check`,
`godot_enable_toolset`). The mapping is applied centrally and enforced by a
contract test.

## 5. Honesty fields

Results carry structured self-reporting that reads as ground truth:

| Field | On | Meaning when it matters |
|-------|----|-------------------------|
| `persisted` + `reason` + `hint` | most mutations | whether a scene save will keep the change; `instanced_child_not_editable`, `node_not_owned`, `embedded_in_other_resource`, `group_from_base_scene` are the reason tokens |
| `undoable` | `batch_set_property` | `false` above 20 nodes — undo will **not** revert the batch |
| `aborted_at`, `skipped_count`, `hint` | `run_commands` | which sub-command stopped the batch and how many never ran |
| `rescan_pending` | `get_parse_errors` | the editor's rescan hadn't flushed; a fresh-class_name error may be stale cache |
| `reason` (readiness) | poll-based tools | why the tool is still pending (`capture_pending`, `scan_in_flight`, …) |
| `scanning` | `asset_import_get_status`, `rescan_filesystem` | the editor's filesystem scan is in flight |

## 6. Contract versioning

`godot_get_server_info` carries `contract_version` (breaking-change counter,
currently **1**) and `min_compatible_contract`. A client is compatible when
`min ≤ client ≤ contract`. Additive changes (new tools, optional fields) never
bump it; removals/renames do. The CalVer build version (`2026.09.19`) moves
every release and is *not* the compatibility signal.

---

Next: [the architecture in depth](architecture/index.md).