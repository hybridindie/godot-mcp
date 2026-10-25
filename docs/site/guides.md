---
type: index
title: "Guides"
description: "Task recipes — build a scene, play-test & debug, verify your work, and ship."
created: 2026-09-19
updated: 2026-10-25
---

# Guides

Task-by-task recipes that show **what to ask** — and, **under the hood**, what your
assistant does at each step. You prompt in plain language and watch it happen in Godot;
the `godot_*` calls are the assistant's, never yours.

- **[Build a scene](guides-build-scene.md)** — scaffold → nodes → script → collision → save, with previews and honest save verdicts along the way.
- **[Play-test & debug](guides-playtest-debug.md)** — the live loop: play the game, inspect it, simulate input, assert state, then break and step through the debugger.
- **[Verify your work](guides-verify.md)** — the verification stack: what each check catches, what it misses, and what to compose for real confidence.
- **[Project-defined tools](guides-project-tools.md)** — expose a project's own operations (spawn a wave, add loot, register a level) as typed, safety-classed `godot_project_*` tools.
- **[Ship: export, tests & CI](guides-ship.md)** — headless export, running the project's test suite, and the CI-shaped verification loop.
- **[Examples](guides-examples.md)** — two complete games under `examples/`, including the debugger demo, to run the toolsets against.

New here? Start with **[your first session](getting-started-first-session.md)**.
