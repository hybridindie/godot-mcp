---
title: Home
description: godot-mcp — drive a live Godot editor from an AI agent over the Model Context Protocol.
---

# godot-mcp

**Bridge an AI agent and a live Godot editor.** Instead of editing files blindly on
disk, the agent drives the editor directly — inspecting, mutating, running, and
verifying a real project over the [Model Context Protocol](https://modelcontextprotocol.io).

[Get started](getting-started/install.md){ .md-button .md-button--primary }
[Why this architecture?](what-why.md){ .md-button }

---

## What it does

| Capability | Toolset |
|------------|---------|
| Inspect the scene tree, selected nodes, and project settings **live** | `inspection` |
| Mutate scenes — create nodes, attach scripts, connect signals — **with undo** | `scene_edit` |
| Edit GDScript and check parse errors deterministically | `scripts` |
| Run the game headless **or** control a live editor play session | `runtime` |
| Simulate input, record replays, assert state, profile performance | `input`, `testing`, `profiling` |
| Export builds, analyze code statically, refactor across scenes | `export`, `analysis`, `batch` |

The server is **game-agnostic** — it knows Godot, not your game. A tower-defense
roguelite, a 3D platformer, and a visual novel all use the same generic tools;
game-specific vocabulary belongs in a separate consumer project.

## How it works, in one picture

<div class="grid cards" markdown>

- :material-arrow-decision: __Four-layer transport chain__

    ---

    AI client → FastMCP server (stdio) → WebSocket bridge → Godot addon → editor.
    The server listens; the editor connects out and reconnects. Every command
    crosses a versioned JSON envelope.

    [Architecture](architecture/index.md)

- :material-lock:{ .lg .middle } __Safety is a product__

    ---

    Every tool carries a safety class (`read_only` / `mutating` / `destructive` /
    `runtime`), destructive tools require `confirm`, previews use `dry_run`, and
    all persistence verdicts are honest about what a save will keep.

    [Safety model](architecture/safety.md)

- :material-shield-lock: __Gated tool surface__

    ---

    192 tools across 29 categories, with only `core` + `inspection` exposed by
    default. The agent enables toolsets as needed — a small surface keeps
    tool-selection sharp.

    [Gating](architecture/gating.md)

- :material-flask: __Verify, don't trust__

    ---

    Headless runs, shader compile checks, parse checks, readiness/reason
    envelopes — the result tells you what a save will keep, and why a tool is
    still pending.

    [Guides](guides/index.md)

</div>

## Status

Feature-complete across the planned ecosystem. Current release:
[2026.09.23](https://github.com/hybridindie/godot-mcp/releases/tag/2026.09.23) —
see the [changelog](changelog.md). MIT licensed.
