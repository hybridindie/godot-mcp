---
type: index
title: "Examples"
description: "Two complete Godot games under examples/ — what they demonstrate, how to run them, and the MCP toolsets they exercise."
created: 2026-09-30
updated: 2026-10-12
---

# Examples

godot-mcp ships two complete Godot 4.x games under
[`examples/`](https://github.com/hybridindie/godot-mcp/tree/main/examples).
They are the reference testbeds: real projects, built through the MCP tools,
that exercise most of the surface end-to-end — and double as worked examples of
the build → verify loop the [guides](guides.md) describe in the abstract.

Both are **geometry-and-color only** (no external art assets), so they are small,
deterministic, and safe to diff.

## `examples/survivors/` — the from-scratch testbed

A survivors-style game built **entirely through the MCP tools** — the canonical
example of the whole authoring path. 60 GUT tests across 8 files.

**Game:** player (WASD movement, health/XP/leveling), enemies (chase AI, per-wave
scaling), projectiles (auto-fire at nearest enemy), XP gems (magnet pickup), a
40×40 checkerboard world with deterministic scattered obstacles, and a HUD.

**Demonstrates:**

| Feature | Toolset(s) |
|---------|-----------|
| Scene tree, nodes, properties | `scene_edit` |
| GDScript authoring + attach | `scripts` |
| Character bodies, collision layers/masks | `physics` |
| Checkerboard grid + obstacle pool | `tilemap` / `scene_edit` |
| HUD bars, labels, overlays | `theme_ui` |
| Autoload game manager + state machine | `resources_edit`, `scripts` |
| GUT unit tests (60) | `testing` |

Run its tests — You: *"Run the survivors unit tests."*

The assistant runs the suite and reports the pass/fail counts (the `testing`
toolset detects GUT automatically — `framework_absent: true` when it isn't
installed).

Or run it yourself:

```bash
godot --headless --path examples/survivors \
  -s addons/gut/gut_cmdln.gd -gexit
```

## `examples/vampire/` — the comprehensive coverage demo

The original Vampire Survivors-style demo, kept as the broadest single project
for toolset coverage — including the **debugger** demonstration.

**Game:** player + health/XP/leveling, projectile and area weapons, enemies with
health bars and wave scaling, an upgrade menu, particles (blood burst, pickup
sparkle), and a `DebuggerDemo` node that trips a real `breakpoint` on input.

**Debugger showcase:** press `Space` (or click in the game window) to hit the
built-in breakpoint, then drive the `debugger` toolset while paused —
`godot_debugger_evaluate_expression(expression=…)` (in the running game's global
scope; the paused-frame stack/vars are not exposed on 4.7, #677),
`godot_debugger_step_into()`, then `godot_debugger_continue_execution()`. See
[Play-test & debug](guides-playtest-debug.md) for the full loop.

**Toolset coverage** (from its README): `scene_edit`, `physics`, `scripts`,
`theme_ui`, `particles`, `tilemap`, `runtime`, and `debugger`.

## How to use an example

Open either project folder in Godot 4.4+ with the godot-mcp addon installed, then treat it
as a target. You prompt in plain language; the assistant makes the calls — the rhythm from
[Your first session](getting-started-first-session.md).

**A few first things to ask:**

- **"Read the scene before you change it."** — the assistant fetches the scene tree and the
  survivors player's properties; every path it sees is call-ready.
- **"Set the Player's speed to 300 — but preview it first."** — the preview carries the same
  save verdict the real run will.
- **"Break into the debugger and step through it."** — on `vampire`, trigger the debugger demo
  and read the stack, exactly as in [Play-test & debug](guides-playtest-debug.md).
- **"Run the survivors tests."** — the suite is a live GUT fixture for the `testing` toolset,
  including the pass/fail parsing.

## Why these exist

They are the **drift catchers**. Because they are real projects driving real
tools, running the toolsets against them surfaces integration failures a unit
test can't: a renamed parameter, a broken `.tscn` round-trip, a physics-layer
regression. A consumer's live eval suites can drive the same projects as its
integration checks.
