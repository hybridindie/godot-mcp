---
type: index
title: "Skills"
description: "The three installable AI skills — what each teaches, how they auto-trigger, and the godot-expert reference guides."
created: 2026-09-30
updated: 2026-09-30
---

# Skills

Beyond tools, prompts, and resources, godot-mcp ships **three installable AI
skills** under [`skills/`](https://github.com/hybridindie/godot-mcp/tree/main/skills).
A skill is client-side knowledge — not an action — that the agent **auto-triggers**
when it recognises a matching task, then routes to the right prompts and tools.

## Skills vs prompts — different jobs

| | Prompts (`/mcp__godot-mcp__build_scene`) | Skills (`godot-getting-started`) |
|---|---|---|
| Who invokes | The user picks a slash command | The **agent** auto-loads on a matching task |
| Shape | A step-numbered recipe naming tools in order | Prose knowledge + rules + a map |
| Lives | In the server (rendered via `render_prompt`) | On disk, installed into the client's skill dir |
| Use for | "Do this specific procedure" | "Know how to work here at all" |

They compose: a skill teaches the model *how the surface works*, and points it
at the prompts for *specific procedures*.

## The three skills

### `godot-getting-started` — the MCP workflow

Read once at the start of any Godot session. Teaches:

- the bridge/version check (`godot_health_check`, `godot_get_server_info`)
- the **toolset-gating model** — enable a toolset before its tools exist
- the safety convention (`read_only` / `mutating` + `dry_run` / `destructive` +
  `confirm` / `runtime`)
- reading the honesty fields (`persisted`, `undoable`, `aborted_at`,
  `rescan_pending`)
- the `godot://` resource surface and the `read_resource` fallback
- round-trip economy (`run_commands`, batch setters)

Triggers on *"use godot-mcp", "drive Godot", "unknown tool from godot"*.

### `godot-playtest-and-debug` — the runtime loop

The two run modes (headless smoke vs live play session), registering the
runtime probe, playing and inspecting the live tree, simulating input,
assertions/stress/screenshots, and the debugger (breakpoints, stepping, frame
variables, expression evaluation). Triggers on *"play-test in Godot", "why does
my game crash", "debug the running scene"*.

### `godot-expert` — engine knowledge

The Godot 4.x rules and pitfalls an expert knows — Control vs Node2D rendering,
z-ordering, the autoload-children trap, input interception, collision
layers/masks, GDScript type inference, `.tscn` format, and the common-bug list.
Triggers on *"build a Godot game", "sprite not showing", "input not working"*.

## The `godot-expert` reference guides

The expert skill loads detail on demand from `references/` — 12 guides, each
"rule → pitfall → the MCP tool shape that applies it":

| Guide | Covers |
|-------|--------|
| `ui-hud.md` | CanvasLayer vs Node2D, anchors/presets, the input-blocking trap |
| `physics-collision.md` | body types, layer/mask convention, collision shapes |
| `autoload-architecture.md` | autoload lifecycle, the children-rendering trap, state machines |
| `scene-authoring.md` | `.tscn` format, disk vs bridge editing |
| `scene-templates.md` | ready-to-use `.tscn` templates |
| `testing-gut.md` | GUT setup, patterns, gotchas |
| `tileset-gridmap.md` | TileSet chain, GridMap + MeshLibrary authoring |
| `visual-shader.md` | VisualShader graph authoring (node ids, port wiring) |
| `shader-authoring.md` | text `.gdshader`, validate-before-assign |
| `theme-styling.md` | theme vs local override, per-state styleboxes |
| `particles-animation.md` | particles, Animation tracks/keyframes, Navigation |
| `common-bugs.md` | documented bugs — symptom, root cause, fix |

## Install

```bash
# opencode (default — symlinks into ~/.config/opencode/skills/):
./scripts/install-skills.sh

# Claude / other clients:
./scripts/install-skills.sh --target ~/.claude/skills

# Standalone copy (packaging a release, no repo dependency):
./scripts/install-skills.sh --copy
```

Symlink (the default) is best during development — repo updates flow through.
Restart the client after installing; skills activate automatically on their
triggers.

## These skills stay honest

The skills are part of the product surface and are **pinned to the live
toolsets** by `tests/unit/test_skills_metadata.py`:

- every `godot_*()` call a skill shows must resolve to a real tool
- the getting-started quick-map must name every registered toolset
- every registered prompt must appear in a workflow skill
- every `references/*.md` guide must be linked from its `SKILL.md`
- the skills and their README must name the current server version

So a surface change without a skills update fails the test suite — the skills
cannot silently drift from the tools they teach.
