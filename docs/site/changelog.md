---
type: index
title: "Changelog"
description: "Release history for godot-mcp."
created: 2026-09-19
updated: 2026-10-20
---

# Changelog

Full release notes live on
[GitHub Releases](https://github.com/hybridindie/godot-mcp/releases). This page
summarizes the recent ones.

## 2026.10.20.1 — Godot 4.4 floor + non-default addon installs

Patch release. Makes the shipped addon load on Godot 4.4–4.6 and work from
non-standard install paths; no tool or contract changes.

- **The addon loads on the 4.4 floor (#738)** — `EditorInterface.get_unsaved_scenes()`
  (4.7+) and `close_scene()` (4.5+) are now resolved dynamically, so no handler
  breaks parsing on 4.4–4.6. The output logger (`extends Logger`, 4.5+) is compiled
  from an embedded source string instead of shipping as a `.gd` file the 4.4 editor
  parses; `ActiveScene` gains `dirty_known`, and moving an open scene is refused when
  the engine cannot report dirty state.
- **Addon-relative paths (#742)** — `command_router.gd` and `mcp_bridge.gd` read
  `plugin.cfg` from their own `resource_path`, so installs under e.g.
  `res://godot/addons/godot_mcp/` report the real addon version.
- **CI** — a `godot-floor` job parses the addon in a real Godot 4.4 editor and runs
  the 26 headless smokes; the live-editor e2e now triggers only for addon-affecting
  changes.

## 2026.10.20 — Editor API autoloads, atomic scaffolds, and replaced-editor recovery

Addon reliability release. Surface: **194 tools** across **29 categories**
(unchanged); all changes are additive — `contract_version` stays 1.

- **Autoloads use the editor API (#700)** — `register_autoload` and
  `unregister_autoload` now go through
  `EditorPlugin.add_autoload_singleton()` / `remove_autoload_singleton()`, so the
  Autoload settings panel refreshes and the change lands on the editor undo
  stack. Headless contexts keep the `ProjectSettings` fallback, and save errors
  are still surfaced.
- **`project_scaffold` is all-or-nothing (#700)** — it snapshots settings,
  files, and directories, validates `main_scene` as an identifier, defers the
  settings save to the end, and rolls back on any failure. A mid-scaffold
  failure now returns a structured `INTERNAL_ERROR` naming the failed step and
  whether rollback completed.
- **Replaced editors recover automatically (#702)** — after `PEER_REPLACED`,
  the addon no longer stays dark forever. It probes a non-displacing `/probe`
  path with a slow 5s→30s backoff; busy probes never displace the active
  editor, and a free probe is adopted as the same connection.
- **The addon ships its license (#728)** — `godot/addons/godot_mcp/LICENSE`
  carries the MIT license into the release/Asset Store zip, as Godot's Asset
  Library guidance recommends.
- **Docs & release workflow** — the compatibility contract is now a dedicated,
  corrected explainer; the docs use the **Godot Editor MCP** product name with
  explicit creator/developer tracks; the legacy Asset Library publish job was
  removed in favor of attaching the addon zip to the GitHub release for manual
  upload to the new store (#723/#725/#727/#734).

## 2026.10.15 — Security hardening, honest results, and a leaner agent surface

A deep review pass across the whole server and addon: the safety/permission model is now
enforced end to end, partial failures are reported honestly instead of as success, the
debugger tells the truth about what the engine cannot do, and the tool surface is easier
for an agent to select from. Surface: **194 tools** (unchanged). Shape is additive —
`contract_version` stays 1 — with one behavioural note below.

- **Security (#634–#638, #649, #650)** — `run_commands` now enforces each sub-command's own
  safety class; the bridge authenticates a new peer *before* evicting the active one; the
  WebSocket/HTTP listeners check `Origin`/`Host`; every file-path parameter is contained to
  `res://`; the safety-class audit reclassified six tools (`create_resource`, `set_setting`,
  `register_autoload`/`unregister_autoload`, `cross_scene_set_property`, `disconnect_signal`)
  as **`destructive`** and made code-execution/disk-write tools approval-gated with a
  **fail-closed** default; the publish workflow builds the tagged commit, gates on tests,
  and pins actions by SHA; every CI job guards against fork PRs.
- **Honest results (#640–#645, #670/#671)** — asset edits land in the scene undo history;
  `type_coerce` covers the full shape set and property writes are verified by read-back;
  `own_recursive` no longer descends into instanced sub-scenes; the over-threshold batch
  path marks the scene dirty; a timed-out mutation is flagged `may_have_applied`;
  `cross_scene_set_property` validates tabs and ownership; runtime and debugger reads are
  request-scoped so a stale reply cannot be mistaken for the current one.
- **Debugger & runtime (#677, #648)** — `evaluate_expression` runs in-game through the
  probe; `get_stack_frames`/`get_frame_variables` return a structured `UNSUPPORTED` on
  Godot 4.7 instead of a wrong answer; the probe stays parseable on the 4.4 floor.
- **Reliability & lifecycle (#655, #675, #647, #646, #683)** — bridge/runtime lifecycle
  leaks closed; the leaked runtime-probe autoload is removed from the project; addon scan
  re-entrancy, oversize replies, and property type names fixed; autoload names validated
  and save errors surfaced; visual-shader create is redoable.
- **Agent experience (#652, #653, #654, #691)** — every tool reference in hints and
  docstrings resolves; tool schemas gained description budgets and enums; known-shape
  `dict` params are typed; `enable_toolset` accepts a bundle (`author`/`playtest`/`ship`) or
  a comma-separated list, collapsing the setup loop to one call.
- **CI & docs (#651, #672, #656)** — live-editor e2e coverage closed and the play-session
  e2e runs under a virtual display; a portable hook plus a version-consistency test keep
  the CalVer copies in lockstep; docs, skills, and examples refreshed against the final
  surface.

> **Behavioural note:** the six tools moved to `destructive` now require `confirm=True`
> (default `False`). Calls that omitted it and previously succeeded must now pass it.

## 2026.10.12 — Version awareness, a resilient addon, and a friendlier site

The server can now tell you when it — or the addon — is out of date, the addon can no longer
silently drop an import, and the docs are rebuilt around getting you to a first working session
fast. Surface: **194 tools** (one new). Additive — `contract_version` stays 1.

- **Version drift & update check (#629)** — `godot_health_check` and `godot_get_server_info`
  report the connected addon's version and flag a server↔addon mismatch; a new
  `godot_check_for_updates` tool (opt-in via `GODOT_MCP_CHECK_UPDATES`, off by default — no
  silent phone-home) reports whether a newer release exists, and a known update is surfaced in
  `get_server_info` and the editor dock.
- **Reliable asset import (#628)** — `godot_asset_import_asset` no longer silently drops its
  filesystem scan when one is already in flight: the addon defers and re-issues it, so a
  freshly copied asset actually imports (and reports `scan_deferred` when it queued one).
- **The addon is "Godot Editor MCP - Addon"** — its in-editor plugin name and its Godot Asset
  Store listing now match.
- **A friendlier site** — a creator-first home, a getting-started path that leads with the
  **skill** (so your assistant enables toolsets itself), and a clearer split between the
  hands-on guides and the deep "Under the hood" reference. The `godot_*` calls are the
  assistant's; the docs no longer ask you to type them.

## 2026.10.10 — Gating that works on the sessionless protocol

Toolset gating now works end to end on the `2026-07-28` sessionless protocol, and the
server no longer trusts the client to refresh its tool list. Surface: **193 tools**
(unchanged). Additive — `contract_version` stays 1.

- **`subscriptions/listen` served and advertised (#620)** — the server registers a
  `ListenHandler` (backed by an in-memory bus) on FastMCP's low-level server, so the
  modern handshake advertises `tools.listChanged: true` and a subscribing client
  receives `notifications/tools/list_changed` after a toggle. Previously the flag was
  advertised as `false` on the modern era, so capable clients (Claude Code CLI) never
  subscribed.
- **Self-sufficient enable result (#621)** — `godot_enable_toolset` returns each enabled
  tool's name, description, and input schema, so a client that ignores the notification
  (most of them) can still call the tools straight from the result.
- **Fire-and-forget dock push (#624)** — the editor dock's toolset row is pushed with the
  new `Bridge.notify` (no awaited reply), so a silent addon no longer stalls
  `enable_toolset`/`disable_toolset` for the 10s request timeout.
- **MCP stack upgrade (#622)** — FastMCP `4.1.0` / `mcp` `2.3.0`, with
  `ResultValidationMiddleware` adapted to FastMCP 4.1's `_ToolBodyError` body-error tag so
  a result-shape mismatch stays a structured `INTERNAL_ERROR`.
- **Front-door README + cleanup** — the README is now a short landing pointing at this
  docs site; stale historical docs and non-OpenCode harness artifacts were dropped.

## 2026.09.30 — Dock feedback, peer-replacement notice, authoring docs

The editor dock becomes a trustworthy supervisor's view, plus two additive
bridge-contract changes and a documentation pass. Surface: **193 tools**
(unchanged). Additive — `contract_version` stays 1.

- **Dock logs command outcomes (#589)** — the recent-command log is fed from
  completion, not dispatch: `✓` on success, `✗ <ERROR_CODE>` on failure, so a
  failed command reads differently from a successful one.
- **Replaced-editor state (#593)** — when a second editor takes over the
  bridge, the server sends the replaced peer a `PEER_REPLACED` notice before
  closing it; the dock shows a distinct **"Replaced by another editor"** state
  (never a misleading green) and stops reconnecting. New additive error code
  `PEER_REPLACED`; reconnect attempts and auth refusals now land in the dock
  log too.
- **Visible UndoRedo guarantee (#590)** — a "Last action" row shows the most
  recent undoable change and how to revert (Ctrl+Z).
- **Dirty-scene + play/probe rows (#591)** — the scene row marks unsaved edits
  (`main.tscn ●`); a "Playing" row shows the running scene and probe state.
- **Toolsets row fed from the server (#592)** — `cmd_toolsets_update` pushes the
  enabled-set on connect and after every toggle, so the dock no longer shows a
  permanent `(none)` (unknown until the first push, honestly).
- **Dock log polish (#594)** — depth 10 → 50 (survives a 20-command batch), a
  *Copy recent commands* button, and a session-scoped command count.
- **Skills: correctness + authoring guides (#611, #614)** — dropped stale
  hardcoded counts (defer to the live inventory), documented the `godot://`
  resource surface, fixed the per-project addon guidance, and added five
  authoring reference guides to `godot-expert` (TileSet/GridMap, VisualShader,
  text shaders, theme/UI, particles/animation/navigation).

## 2026.09.28 — One-shot runtime reads, screenshot transport, probe hardening

Robustness and honesty pass over the runtime-session surface, plus one new
tool. Surface: **193 tools** (was 192; +`godot_runtime_read_property`). All
changes additive — `contract_version` stays 1.

- **Dedicated one-shot property read (#571)** — `godot_runtime_read_property`
  (`read_only`): reads a live property once without disturbing the monitor
  capture; mid-capture reads and stale-`request_id` polls are safe (#577).
- **Full-screenshot transport (#563)** — raised WebSocket buffer caps on both
  sides so full-resolution captures transfer instead of truncating.
- **Probe runs while paused (#565)** — the runtime probe keeps processing
  frames while the SceneTree is paused, so captures don't stall behind a
  `get_tree().paused` game.
- **Physical-keycode binding probe (#570)** — injected keys match
  physical-keycode (`KEY_`) bindings, not just keycode ones.
- **Result models are JSON-strict (#580)** — addon-produced fields on result
  models are strictly typed; malformed bridge payloads surface as
  `INTERNAL_ERROR` instead of passing through (#567).
- **`ui_elements` replies gated on the pending request_id (#577)** — a stale
  capture's late reply can no longer resolve the wrong waiter.
- **CI hardening (#579, #583, #587)** — setup-uv pinned (no manifest fetch),
  the e2e suite bounded with `timeout --kill-after`, stray godot processes
  reaped; previously-unverified smokes wired into CI.
- **Proactor `ConnectionResetError` demoted to DEBUG (#572)** — benign
  disconnect noise no longer logs at ERROR.
- **Timer-based filesystem auto-refresh (opt-in)** — the editor can pick up
  external edits on a timer; off by default.
- **Class info accepts Variant-shaped defaults (#564)** —
  `describe_class` no longer chokes on Variant-typed property defaults.

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