---
type: index
title: "For creators"
description: "Make a Godot game by talking to your AI assistant. Set up Godot Editor MCP once, then build, run, and verify inside your real editor."
created: 2026-10-18
updated: 2026-10-18
---

# For creators

**You make games. You want an AI assistant to help inside the editor you already use.**
This track gets you there without learning MCP or typing tool names.

Godot Editor MCP connects your AI assistant to the **live Godot editor** through a small
addon. The assistant can inspect the scene you can see, create and edit nodes, write
GDScript, run the game, and check its own work. Every change lands on Godot's own undo
stack, so **Ctrl+Z works exactly as it does for you**.

## What you need

- **Godot 4.4 or newer**, with your project open.
- An AI assistant that can **run commands and edit files** — for example Claude Code,
  OpenAI Codex, or OpenCode.
- That's it. The assistant installs Godot Editor MCP for you.

## Start here

1. **[Set up with your AI agent](getting-started-with-an-agent.md)** — one copy-paste
   prompt installs the server, the addon, and the skills. You do one click.
2. **[Your first session](getting-started-first-session.md)** — the orient → enable →
   preview → act → verify rhythm, in plain language.
3. **Describe what you want** — *"add a player that jumps"*, *"make the jump feel
   snappier"*, *"why does it crash on start?"*.

## Then build

- **[Build a scene](guides-build-scene.md)** — scaffold, nodes, script, collision, save.
- **[Play-test & debug](guides-playtest-debug.md)** — play the game, simulate input,
  inspect live state, and step through the debugger.
- **[Verify your work](guides-verify.md)** — what each check catches and what it misses.
- **[Ship: export, tests & CI](guides-ship.md)** — export builds and run tests headlessly.
- **[Examples](guides-examples.md)** — two complete games to learn from.

## What the assistant can do

| You say… | What happens in Godot |
|----------|-----------------------|
| "build / change a scene" | nodes, properties, and signals — with undo |
| "write / fix this script" | GDScript written into your project, with a parse check |
| "run it and tell me what breaks" | the game runs; errors and warnings come back |
| "test that X works" | live checks and screenshots |
| "export a build" | Web / desktop builds |

## What to expect

- **It asks before destroying.** Deleting or overwriting needs your OK first; previews
  are free.
- **Everything is undoable.** The assistant's changes sit on the same undo stack as
  yours.
- **It reports what will really be saved.** An edit can show in the editor but not persist
  if it lands inside an instanced scene. The result says so, with a fix.
- **It cannot see your screen by itself.** A vision-capable assistant can screenshot the
  editor or the running game to look at the scene, but it cannot watch you — answer its
  questions and keep an eye on the editor.

## If something is off

| What you see | What to do |
|--------------|------------|
| "Godot bridge is not connected" | Open Godot with the addon enabled; check the dock dot is green. |
| The dock dot stays grey or red | Restart Godot, or toggle the plugin off and on. |
| "unknown tool" | Ask the assistant to *"enable the toolset it needs first"*. |
| It broke after an update | Ask the assistant to reinstall the addon from the latest release. |

Still stuck? Point the assistant at the [workflow prompts](reference-prompts.md),
especially `troubleshoot`.

---

**Technical reader?** The [developer track](for-developers.md) covers the architecture,
the tool contract, and how to extend or contribute.
