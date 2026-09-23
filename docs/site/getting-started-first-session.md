---
type: index
title: "Your first session"
description: "Orient → enable → preview → act → verify — the shape of every good godot-mcp session."
created: 2026-09-19
updated: 2026-09-23
---

# Your first session

A well-run godot-mcp session has a rhythm: **orient → enable → preview → act →
verify**. Each stage uses a different slice of the surface.

## 1. Orient (always-on `core`)

```
godot_health_check()        # bridge connected? which version?
godot_get_server_info()     # capability snapshot: toolsets, active scene, next_steps
godot_list_toolsets()       # what exists, what's enabled, min Godot per toolset
```

`godot_get_server_info` is the single most useful call: its `next_steps` field
usually names the fix for whatever is wrong.

## 2. Enable what you need

Only enable the toolsets the current task needs — right before you need them:

```
godot_enable_toolset('scene_edit')    # creating nodes, properties, signals
godot_enable_toolset('scripts')       # reading/writing GDScript
```

Gated tools return a structured error naming the missing toolset — the fix is
one `enable_toolset` call away. `godot_list_toolsets()` is authoritative.

## 3. Inspect before you mutate

```
godot_inspection_get_scene_tree()          # the tree; paths are tool-ready
godot_inspection_get_selected_node()       # what the human is looking at
godot_inspection_get_project_info()        # autoloads, input actions, main scene
```

Node paths come back scene-relative (".", "Player/Weapon") in exactly the form
the path-taking tools accept — pass them verbatim.

## 4. Preview, then act

```
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D",
                             node_name="Player", dry_run=true)
# preview: {node_path: "Player", created: false, persisted: <verdict>}
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D", node_name="Player")
# real:   {node_path: "Player", created: true, persisted: true}
```

`dry_run` runs the same preconditions and persistence probe the real run will —
use it on unfamiliar scenes. Every mutation is undoable: `godot_undo()`.

## 5. Verify

```
godot_scripts_get_parse_errors(script_path='res://scripts/player.gd')
godot_runtime_run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)
```

A clean parse is *not* full verification — runtime API misuse needs the
headless run. Shaders need `godot_shader_validate`. The one-call diagnostics
recipe is `godot_debug_workflow()` (always-on `core`).

## Reading the results

- `persisted: true` → the save will keep the change.
- `persisted: false, reason: instanced_child_not_editable` → act on the hint:
  `godot_scene_edit_set_editable_children(node_path='Relic')`, or retarget.
- `rescan_pending: true` on a parse check → re-check once; the editor's scan
  hadn't flushed.
- `aborted_at` on a batch → trailing commands did **not** run.

## When something fails

| Error | Meaning | Fix |
|-------|---------|-----|
| `unknown tool` | toolset not enabled (or a server-side tool confused with an editor tool) | `godot_enable_toolset(...)` |
| `PRECONDITION_FAILED [required=active_scene]` | no scene open | `open_scene` / `create_scene` |
| `PRECONDITION_FAILED [required=confirm]` | destructive call needs confirmation | pass `confirm=True` (after `dry_run`) |
| `BRIDGE_DISCONNECTED` | editor not reachable | open Godot + addon; check the status dock |
| `VALIDATION_ERROR` with a did-you-mean | typo'd key/path | use the suggested key |

`godot_get_server_info()`'s `next_steps` and the `troubleshoot` prompt cover
the rest.