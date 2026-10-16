---
type: index
title: "Play-test & debug"
description: "The live loop — play, inspect, simulate input, assert, break and step through the debugger."
created: 2026-09-19
updated: 2026-10-12
---

# Play-test & debug

The live loop against a real running game. You ask in plain language; the assistant does the
rest. Requires the `runtime`, `input`, `testing`, and `debugger` toolsets plus the
`MCPRuntimeProbe` autoload in the game's project.

## Two run modes — pick the right one

::: info Under the hood
A **headless** run spawns a separate Godot process — a quick "does it even boot" smoke, no
editor, no probe. A **live play session** drives the game *inside* the running editor, so you
can inspect and steer it. The rest of this page is the live loop.
:::

| Mode | Toolset | Answers |
|------|---------|---------|
| Headless smoke test | `runtime` | "does it run at all" — no editor play session, no probe |
| Live play session | `runtime` + `input` + `testing` + `debugger` | interactive inspection, input, assertions, breakpoints |

For a one-call report that covers the headless side, just ask the assistant to "run the debug
workflow" — that needs no extra toolset.

## 1. Register the runtime probe

You: *"Set up live runtime inspection — add the probe autoload if it's missing."*

The assistant checks the project's autoloads and, if the probe isn't registered, adds it. The
probe runs **in the game** (not the editor) and no-ops in exported builds.

## 2. Play and inspect

You: *"Play the main scene and show me the Player's position over time."*

The assistant starts a live play session, then can read the running game's real hierarchy (not
the editor's copy), sample a property over frames, find UI by its text, and read performance
monitors. Pending reads carry a `reason` token (e.g. `capture_pending`) — the assistant keeps
polling rather than re-issuing.

## 3. Simulate input

You: *"Hold right, release, then press Space."*

The assistant synthesizes key, mouse, and action input into the running game, can replay a
recorded sequence or record a macro, and reports how many events the game acknowledged. While
the game is **paused at a debugger break, input is refused** — the assistant continues
execution first. A frozen injected count is the pause signal, not a bug.

## 4. Assert state

You: *"Assert the Player is visible, then fuzz it with random input."*

The assistant asserts live node state, runs a scripted scenario (a sequence of events plus
assertions), fuzzes with random input, and compares screenshots — so behavior is checked, not
just "it didn't crash".

## 5. Break and step

You: *"Set a breakpoint on player.gd line 42 and step through it."*

The assistant sets a breakpoint; breakpoints fire on their own line. A forced break lands
on the probe's next frame (no game cooperation needed). Once stopped, it can step
over/into/out, evaluate an expression in the running game (`evaluate_expression` — global
scope, not frame-scoped), and continue. The paused-frame stack / variable dump
(`get_stack_frames`, `get_frame_variables`) is **not available on Godot 4.7** (#677).

## Debugging failures

| Symptom | First move |
|---------|-----------|
| Crash on play | ask for a headless run and read the errors/warnings |
| `timed_out: true` | not a crash — games that never self-quit always time out; tell the assistant the timeout is expected |
| Script "won't parse" | ask for a parse check; if it flags `rescan_pending`, re-check before "fixing" |
| Input does nothing | is the game playing? is the probe registered? a full-screen overlay eating input? paused at a break? |
| Stuck | ask the assistant for the server info's `next_steps`, or use the `troubleshoot` prompt |

Ask the assistant to stop the play session when you're done.
