---
type: index
title: "Your first session"
description: "Driving a real Godot project from an AI harness — the orient → enable → preview → act → verify rhythm."
created: 2026-09-19
updated: 2026-09-30
---

# Your first session

godot-mcp is driven **through an AI harness**, not by typing tool names. You
describe what you want in the editor's terms; the agent in your client (OpenCode,
Claude, or any MCP host) issues the `godot_*` tool calls and reads the results
back. You supervise in Godot — the status dock and the undo stack are the
human's view of what the agent did.

Every stage below shows **what you ask** and **what the agent calls under the
hood** (so you can follow along, and know what to expect in the editor). The
rhythm is always the same: **orient → enable → preview → act → verify.**

## 1. Orient — ask the agent to check the bridge

You: *"Check that Godot is connected and tell me what's available."*

```
godot_health_check()        # bridge connected? which version?
godot_get_server_info()     # capability snapshot: toolsets, active scene, next_steps
godot_list_toolsets()       # what exists, what's enabled, min Godot per toolset
```

If the agent reports `bridge_connected: false`, the editor isn't reachable —
open Godot with the [addon enabled](getting-started-addon.md), check the status
dock (bottom panel), and ask again. `godot_get_server_info` is the single most
useful call: its `next_steps` field usually names the fix for whatever is wrong.

## 2. Enable what you need — the agent must turn toolsets on

You: *"Add a Player node to the main scene."* — the agent discovers it can't,
because only `core` + `inspection` are exposed by default.

```
godot_enable_toolset('scene_edit')    # creating nodes, properties, signals
godot_enable_toolset('scripts')       # reading/writing GDScript
```

Gated tools return a structured error naming the missing toolset; the agent's
fix is one `enable_toolset` call. `godot_list_toolsets()` is authoritative.
Your job here is nothing — a well-behaved agent enables the toolset itself and
tells you it did. (If it stalls on `unknown tool`, prompt it: *"enable the
toolset you need first."*)

## 3. Inspect before mutating — the agent reads, then edits

You: *"What's in the scene right now?"*

```
godot_inspection_get_scene_tree()          # the tree; paths are tool-ready
godot_inspection_get_selected_node()       # what you have selected in the editor
godot_inspection_get_project_info()        # autoloads, input actions, main scene
```

Node paths come back scene-relative (`"."`, `"Player/Weapon"`) in exactly the
form the path-taking tools accept — the agent passes them verbatim. You can see
the same thing live in Godot's Scene dock.

## 4. Preview, then act — you approve, the agent mutates

You: *"Create the Player node — preview it first."*

```
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D",
                             node_name="Player", dry_run=true)
# preview: {node_path: "Player", created: false, persisted: <verdict>}
godot_scene_edit_create_node(parent_path=".", node_type="CharacterBody2D", node_name="Player")
# real:   {node_path: "Player", created: true, persisted: true}
```

`dry_run` runs the same preconditions and persistence probe the real run will —
worth asking for on unfamiliar scenes. When the agent acts, the change lands in
**your** editor: watch it appear in the Scene dock, and press **Ctrl+Z** to
undo it. Every mutation is on the editor undo stack, so the agent's actions are
as revertible as your own.

## 5. Verify — ask the agent to prove it worked

You: *"Check the script parses and the scene runs without errors."*

```
godot_scripts_get_parse_errors(script_path='res://scripts/player.gd')
godot_runtime_run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)
```

A clean parse is *not* full verification — runtime API misuse needs the headless
run. Shaders need `godot_shader_validate`. The one-call diagnostics recipe is
`godot_debug_workflow()` (always-on `core`). Ask for the verdict, not just the
action.

## Reading the results the agent reports back

The agent's results carry **honesty fields** that read as ground truth — check
them (or ask the agent to explain them):

- `persisted: true` → the save will keep the change.
- `persisted: false, reason: instanced_child_not_editable` → the edit shows in
  the editor but **won't be saved**; act on the hint
  (`godot_scene_edit_set_editable_children(node_path='Relic')`), or retarget.
- `rescan_pending: true` on a parse check → the editor's file scan hadn't
  flushed; re-check once before "fixing" correct code.
- `aborted_at` on a batch → trailing commands did **not** run.

A well-behaved agent reads these and acts; you should ask it to when it doesn't.

## When something fails

| Error | Meaning | What to tell the agent |
|-------|---------|------------------------|
| `unknown tool` | toolset not enabled (or a server-side tool confused with an editor tool) | "enable the toolset first" |
| `PRECONDITION_FAILED [required=active_scene]` | no scene open | "open or create a scene" |
| `PRECONDITION_FAILED [required=confirm]` | destructive call needs confirmation | review it, then "confirm and retry" |
| `BRIDGE_DISCONNECTED` | editor not reachable | open Godot + addon; check the status dock |
| `VALIDATION_ERROR` with a did-you-mean | typo'd key/path | "use the suggested key" |

`godot_get_server_info()`'s `next_steps` and the `troubleshoot` prompt cover the
rest.

## Making it smoother

- **Install a skill.** The bundled [skills](reference-skills.md)
  (`godot-getting-started`, `godot-expert`, …) auto-trigger in the client and
  teach the agent this rhythm, the toolset gating, and the Godot pitfalls — so
  you prompt in plain language, not in tool names.
- **Reach for prompts.** The server's [workflow prompts](reference-prompts.md)
  (`/mcp__godot-mcp__build_scene`, `/play_test`, …) are step-numbered recipes the
  agent can follow for a whole task.
- **Start from an example.** The two games under
  [examples](guides-examples.md) give the agent a real project to work against.

Next: [Build a scene](guides-build-scene.md) walks the full loop, or
[Play-test & debug](guides-playtest-debug.md) starts from the runtime side.
