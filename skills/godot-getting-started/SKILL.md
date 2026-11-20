---
name: godot-getting-started
description: "Use at the start of any task in a Godot project when the Godot Editor MCP tools are available — writing or editing scripts, adding or changing nodes and scenes, setting properties, attaching scripts — and whenever a Godot MCP tool is missing or refused. Teaches the version check, toolset gating (enable a toolset before its tools exist), the dry_run/confirm safety convention, and how to verify the bridge."
---

# godot: getting started

Godot Editor MCP exposes the Godot editor (inspection, scene edits, scripts, runtime) over MCP. This skill documents the **2026.11.04b2** surface. Tools are named `godot_<toolset>_<action>`. The live inventory is authoritative — `godot_get_server_info()` and `godot_list_toolsets()` report the real tools and categories, so trust them over anything written here. Read this once at the start of a Godot session — it prevents the three most common failures: a version mismatch, missing tools, and unconfirmed destructive edits.

## 1. Confirm the bridge and the version

The server talks to a running Godot editor over a WebSocket bridge. If Godot isn't open with the addon enabled, every editor tool fails.

```
godot_health_check()      # bridge connected? which URL? → also returns version
godot_get_server_info()   # version, contract_version, toolsets, active scene, next_steps
```

- `godot_health_check()` returns `version` — if it isn't **2026.11.04b2**, this skill may be stale; rely on `godot_get_server_info()`'s live toolset/tool inventory over anything here.
- `godot_get_server_info()` returns `contract_version` (tool-surface compatibility, currently 1) — a client is compatible when `min_compatible_contract <= yours <= contract_version`.
- **Version drift & updates.** `godot_health_check()` / `godot_get_server_info()` report the connected addon's version and flag a server↔addon mismatch (`version_notice`) — if the two differ, both sides need the same release. If update checks are enabled (`GODOT_MCP_CHECK_UPDATES`), call `godot_check_for_updates()` to see whether a newer Godot Editor MCP release exists; a known update also shows up in `next_steps`.
- If disconnected: open **your Godot project** with the addon enabled (addons are installed per-project; for a smoke test you can open the `godot/` folder of the Godot Editor MCP checkout). Requires Godot 4.4+ (the beta line is validated on 4.8-beta2; the stable line validates 4.7). Enable it in Project Settings → Plugins → godot_mcp, then check the status dock.

## 2. Toolsets are gated — enable before you use

Only `core` (always on) and `inspection` (read-only) are enabled by default — unless the server was started with `GODOT_MCP_DEFAULT_TOOLSETS` seeding more (check `godot_list_toolsets()` for the live state; it is authoritative). **Every toolset reported disabled is hidden until you enable it.** Calling such a tool returns `unknown tool` — there is no fallback. Some toolsets require Godot 4.4+ (`scene_edit`, `input_map`, `tilemap`, `scene_3d`); `godot_list_toolsets()` reports `min_godot` per toolset.

```
godot_list_toolsets()                 # what exists / what's enabled / min Godot
godot_enable_toolset('scene_edit')    # turn on what you need, then call its tools
```

Quick map of the gated toolsets (`godot_list_toolsets()` is the authoritative list):

- **Scene building** — edit nodes/scenes/signals → `scene_edit` · macro edits in one round-trip → `composite` · extract a subtree into a reusable .tscn prefab (replace-with-instance) → `scene_edit_extract_scene` · 3D scenes (meshes, cameras, lights, GridMap) → `scene_3d` · UI themes → `theme_ui` · tilemaps → `tilemap` · particles → `particles` · navigation → `navigation` · physics → `physics` · animation → `animation` · audio buses → `audio` · shaders → `shader` · visual shader graphs → `visual_shader`
- **Code & data** — GDScript files → `scripts` · C# files (read/list/write; `.cs` needs a build to be usable — check `godot_get_server_info().bridge.backend`) → `scripts` · resources (.tres) + autoloads → `resources_edit` · project files/settings/UIDs → `project` · move/rename a project file with dependency remap → `godot_project_move_file` · new project skeleton → `project_scaffold`
- **Run & verify** — headless run + output capture → `runtime` · live play-test + input sim → `input` · input actions in project settings → `input_map` · automated assertions/screenshots → `testing` · breakpoints/stepping → `debugger` · performance monitors → `profiling`
- **Bulk & ship** — batch/cross-scene ops → `batch` · static analysis → `analysis` · export presets → `export` · import external assets → `asset_import` · editor screenshots (vision clients) → `editor`

Always-on `core` extras: `godot_describe_class` (ClassDB metadata — check property/method names before setting), `godot_undo` (undo the last editor action), `godot_redo` (re-apply an undone action — `godot_list_history()` orients first), `godot_checkpoint_create()` / `godot_checkpoint_restore(checkpoint_id=…)` (mark and undo back to a point in editor history), `godot_vcs_snapshot()` / `godot_vcs_restore(snapshot_id=…)` (the backstop for edits the undo stack does not cover), `godot_describe_tool(tool, args)` (mint the `consent` token a destructive call requires when approval is configured), `godot_list_tools_by_safety_class()`, `godot_debug_workflow()` (diagnostics recipe), the toolset tools, and the two checks above.

`godot_composite_compose_node(parent_path=…, node_type=…, node_name=…, properties=…, script_path=…, children=…)` is the create-with-config macro: one round-trip, one UndoRedo action. The primitive `godot_scene_edit_create_node` takes only parent, type, and name.

## 3. The safety convention

- **Read-only** tools never mutate — no flags needed.
- **Mutating** tools accept `dry_run=True` — they report what *would* change and do nothing. Preview when unsure.
- **Destructive** tools (delete/overwrite, e.g. `godot_scene_edit_delete_node`) require `confirm=True` or they refuse; they also support `dry_run`.
- **Runtime** tools control game execution (play/stop/breakpoints) — no `dry_run`.

Read results as ground truth, not decoration: every mutation carries a `receipt` (what changed, before/after where available) and `reversible_by` (`undo` / `vcs` / `none`); batch results carry honesty flags — `godot_batch_set_property` returns `undoable` (false above 20 nodes: undo will NOT revert it), `godot_composite_run_commands` reports `aborted_at`/`skipped_count` when it halted early, and a `TIMEOUT` on a mutating tool returns `may_have_applied: true` (the editor runs commands serially, so re-read state before retrying — never double-apply) — and `godot_scripts_get_parse_errors` returns `rescan_pending` (a fresh-class_name "Could not find type" may be stale cache; re-check before fixing). Read these fields; they prevent double-work. When `reversible_by` is `vcs`, take a `godot_vcs_snapshot()` before the next large non-undoable edit.

**Verify mutations with snapshot + diff** (read-only, always available): `godot_inspection_snapshot_subtree(node_path)` before a batch edit, `godot_inspection_diff_snapshots(before_id)` after (diffs vs. live state) — one call returns `{added, removed, changed: [{node, property, before, after}]}` instead of N re-reads. Snapshot ids are bounded (`s1`, `s2`, …); an evicted id says so — re-snapshot.

## 4. Use the built-in workflow prompts

The server ships step-by-step recipes as MCP prompts (slash commands like `/mcp__godot-mcp__build_scene`): `toolset_discovery`, `build_scene`, `play_test`, `script_edit`, `debug_scene`, `troubleshoot`, `author_resource`, `export_build`, `batch_refactor`. Reach for them, or use the companion skills `godot-playtest-and-debug` and `godot-expert`.

## 5. Read context as resources (cheaper than tool round-trips)

Besides tools, the server exposes read-only **`godot://` resources** — addressable JSON snapshots of the same context. Prefer them when your client supports resources: the address *is* the context, so you don't spend a tool call re-deriving it.

| Resource URI | What it holds |
|--------------|---------------|
| `godot://project/info` | project name, autoloads, input actions |
| `godot://scene/current` | the active scene (path, name) |
| `godot://scene/tree` | the full scene tree (equivalent to `get_scene_tree(max_depth=-1)`) |
| `godot://scene/tree/{max_depth}` | the tree bounded to `max_depth` levels |
| `godot://node/selected` | the selected node snapshot (`{"selected": null}` when none) |

**Client without resource support?** Call the `godot_read_resource(uri)` tool instead — it is the resources-as-tools fallback and takes the same URIs, e.g. `godot_read_resource(uri='godot://scene/tree')`. An unknown URI returns a structured error naming the valid ones.

Resources are read-only and never mutate; mutations always go through tools.

## A complete small edit (copy this shape)

```
godot_enable_toolset(category="scene_edit")
godot_composite_compose_node(
    parent_path=".", node_type="CharacterBody2D", node_name="Player",
    properties={"position": {"x": 400, "y": 300}},
    children=[{"node_type": "CollisionShape2D", "node_name": "CollisionShape2D"}])
# → {"node_path": "Player", "created": true, "children": ["CollisionShape2D"], ...}

godot_scripts_write(script_path="res://scripts/player.gd", content="extends CharacterBody2D\n...")
godot_scene_edit_attach_script(node_path="Player", script_path="res://scripts/player.gd")
godot_scripts_get_parse_errors(script_path="res://scripts/player.gd")
# → {"errors": [], "rescan_pending": false}

godot_scene_edit_save_scene()
# → {"saved": true, "path": "res://scenes/main.tscn", ...}
```

Read the persistence verdict on each mutation: `persisted: false` means the
save will drop it, and `reason` + `hint` name the fix (usually
`godot_scene_edit_set_editable_children` or retargeting to a node the scene owns).

## When something fails

- `unknown tool` → the toolset isn't enabled (step 2), or you mixed up a server-side tool with an editor tool.
- `PRECONDITION_FAILED` → read `required`:
  - `active_scene` — open a scene (`godot_scene_edit_open_scene` / `create_scene`).
  - `confirm` — add `confirm=True` (preview with `dry_run=True` first).
  - `consent` — `godot_describe_tool(tool, args)`, then pass its `token` as `consent`.
  - `bridge_connected` — step 1.
  - `editor_ready` — the editor is importing/modal/busy; wait, then retry.
  - `play_session` — call `godot_runtime_play_scene(scene_path=…)` first.
  - `runtime_probe` — register `MCPRuntimeProbe` as an autoload.
  - `game_not_breaked` — the game is frozen at a debugger break: `godot_debugger_continue_execution()`.
  - `godot_version` — the toolset needs a newer editor.
  - `godot_bin` — install Godot / set `GODOT_MCP_GODOT_BIN`.
  - `project_dir` — set `GODOT_MCP_PROJECT_DIR` or open the project.
  - `toolset` — enable the tool's toolset.
  - `human_approval` — configure/approve the approval gate.
- `VALIDATION_ERROR` on `godot_project_set_setting` → the hint names the likely intended key (e.g. typo'd `application/config/main_scene` → did-you-mean `application/run/main_scene`).
- `TIMEOUT` on a mutating tool with `may_have_applied: true` → re-read state before retrying; do not double-apply.
- Run `godot_get_server_info()` first — its `next_steps` field usually names the fix.

## Working efficiently

- **Enable only what the task needs, right before you need it** — the exposed surface stays small on purpose; don't pre-enable everything. Enable a whole workflow in **one call** with `godot_enable_toolset("author,playtest")` — `author`/`playtest`/`ship` are bundles that expand to their member toolsets (a bundle is just a preset, not a new category), and you can comma-separate any mix of toolsets and bundles.
- **Batch round-trips**: independent editor operations belong in one `godot_composite_run_commands` call (one editor frame for N commands) instead of N tool calls. Same for bulk property sets (`godot_batch_set_property`) and same-shape node creation (`godot_composite_batch_create_nodes`). Each entry still carries its own tool's policy: enable the sub-command's toolset first, and pass `confirm=true` if the batch contains a destructive sub-command.
- **Verify before you build**: `godot_debug_workflow()` in `core` is one call returning parse errors + scene tree + headless run + bridge state — cheaper than four separate diagnostics calls.
- **`dry_run` first on unfamiliar mutations** — the preview includes the projected honesty flags (`undoable`, persistence verdicts).