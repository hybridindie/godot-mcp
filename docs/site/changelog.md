---
type: index
title: "Changelog"
description: "Release history for godot-mcp."
created: 2026-09-19
updated: 2026-09-23
---

# Changelog

Full release notes live on
[GitHub Releases](https://github.com/hybridindie/godot-mcp/releases). This page
summarizes the recent ones.

## 2026.09.23 — Prefab workflow, snapshot verification, C# authoring

Closes the authoring gaps: the editor's inverse moves, one-round-trip
verification, and C# authoring behind a capability gate. Surface: **192 tools**
(was 184). All changes additive — `contract_version` stays 1.

- **Extract subtree to PackedScene (#531)** — `godot_scene_edit_extract_scene`
  (`mutating`): the editor's "Save Branch as Scene" — packs a subtree into a
  reusable `.tscn`, optionally replacing it with an instance in one UndoRedo
  action; refuses non-owned/mixed-ownership subtrees (#477 family).
- **Move/rename project file (#532)** — `godot_project_move_file`
  (`mutating`): `res://` move with project-wide dependency remap (path + uid
  forms), `.uid` sidecar relocation, uid re-point; structured refusals for
  missing source / existing destination / open-and-unsaved scene; honest
  `undoable: false` with a recovery hint.
- **Snapshot + diff a subtree (#535)** — `godot_inspection_snapshot_subtree`
  + `godot_inspection_diff_snapshots` (both `read_only`): verify a batch
  mutation in one round-trip; server-side bounded LRU store; group changes
  surface as `property: "groups"`.
- **Push-on-change property sampling (#536)** — `monitor_property` dedupes
  unchanged values by default (epsilon-tolerant floats, recursively through
  Vector2/Color shapes); `requested`/`dropped_duplicates`/`sampling_usec`
  honesty stats; `on_change_only=False` restores legacy sampling.
- **Optional bridge auth token (#538)** — `GODOT_MCP_BRIDGE_TOKEN` on both
  sides; the addon authenticates as its first message; a mismatch is refused
  at the handshake with a structured envelope (reconnect loop shows the
  reason); unset = byte-identical no-auth path. Never logged.
- **C# Phase 1 (#207)** — language-aware script authoring: read/write/list
  accept `.cs` (default GDScript, contracts unchanged); `list` gains
  `language=gd|cs`; a `.cs` write carries a validate-via-build hint (never a
  false parse-OK); parse/patch refuse `.cs` until Phase 2 (#560);
  `get_server_info().bridge.backend` surfaces
  `{csharp_supported, csharp_project, csharp_build}`.
- **ClassDB discovery (#533)** — `godot_describe_class`: properties/methods/
  signals for agent discovery before setting.
- **Game console output (#534)** — `godot_runtime_get_game_output`: the
  running game's stdout/stderr/script errors from a bounded ring.
- **Server↔addon handshake (#530/#521)** — `cmd_get_addon_info` cached per
  peer; `get_server_info` exposes `addon_version`/`addon_commands` + a drift
  warning; the dock labels `godot-mcp <ver> / Godot <ver>`.
- **Peer identity (#537)** — the addon announces project path/Godot/addon
  versions at connect; peer replacement is logged naming both paths.
- **Undo/redo parity (#529)** — `godot_redo` + `godot_list_history`.
- Refactors: single-sourced add-child undo commits (#528), unified
  probe/break guards (#526), shared helpers extraction (#546), honest
  `command_completed` exec_ms (#520), prop-cache staleness fix (#540), dock
  status-icon texture cache (#539).

## 2026.09.19 — Persistence truth everywhere + verification tools

Completes the persistence-truth family, formalizes the readiness/reason
envelope, adds the verification tools the "advertised verification" trust gap
needed. Surface: **184 tools** (was 181). All changes additive —
`contract_version` stays 1.

- **Persistence truth for structural edits + batches (#477)** — parent rule for
  13 create-family handlers, destination rule for moves, node rule for
  deletes, per-target `persistence[]` verdicts for `batch_set_property` and
  `apply_node_edits`; live e2e asserts the saved file agrees with every verdict.
- **`godot_scene_edit_set_editable_children` (#487)** — the action the
  `instanced_child_not_editable` hints name; the tree marks instanced nodes
  with `owner` / `editable_children`.
- **Readiness/reason envelope (#456/#457/#459)** — every poll handler carries
  a stable `reason` token; `poll_ready` relays it in timeout errors.
- **`godot_shader_validate` (#423)** — real headless engine compile check;
  `get_parse_errors` documented as syntax-level.
- **Audio effect property echo (#427)** — `get_bus_layout` echoes per-effect
  `properties` (read/write parity).
- **AudioStreamWAV loop settings (#418)** — `import_asset` accepts
  `loop_mode`/`loop_begin`/`loop_end` for `.wav`; `loop_applied` verdict.
- **`godot_scene_edit_rescan_filesystem` (#486)** — pick up external file
  edits non-destructively.
- Skills teach the honesty semantics + round-trip economy (#501).

## 2026.09.17 — Honest reporting & trust-class fixes

- Timeout ≠ crash: no false `NON-ZERO EXIT`; `expected_timeout` param (#490).
- `run_commands` reports `aborted_at`/`skipped_count` on early stops (#437).
- `batch_set_property` reports `undoable` (false above 20 nodes) (#461).
- `set_setting` refuses unknown keys with a did-you-mean hint (#462).
- Input simulation refused while paused at a debugger break (#443).
- `get_parse_errors` gates on the editor's filesystem scan (`rescan_pending`) (#453).
- Addon RefCounted leak cycles fixed (#492, by Vincent Huang).
- `tools/list_changed` emitted on enable/disable (#491).
- Toolset-gating text reflects the effective `GODOT_MCP_DEFAULT_TOOLSETS` (#425).
- OpenWebUI setup guide (#484, by Randall Lasini).

## 2026.09.10 — Game frame capture + silent-failure hardening

- Live game screenshots/frames via the probe; silent-failure fixes across
  persistence previews (#458/#475/#476); debugger session hygiene (#454).

## Earlier

See the [releases page](https://github.com/hybridindie/godot-mcp/releases) for
the full history (2026.09.02 "First Stable", 2026.08.31b4, …).