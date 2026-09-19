---
title: Changelog
description: Release history for godot-mcp.
---

# Changelog

Full release notes live on
[GitHub Releases](https://github.com/hybridindie/godot-mcp/releases). This page
summarizes the recent ones.

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