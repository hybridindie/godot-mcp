---
type: index
title: "Set up with your AI agent"
description: "For creators — have Claude, Codex, or any AI assistant install and connect godot-mcp to your Godot project, then build by describing what you want."
created: 2026-10-11
updated: 2026-10-16
---

# Set up with your AI agent

**You don't need a terminal, and you don't need to know what MCP is.** This page is
for people who make things in Godot and use an AI assistant (Claude, Codex, ChatGPT…).
The assistant does the setup; you make the game.

> Already comfortable with terminals and MCP? The [technical setup](getting-started-install.md)
> and the [architecture](architecture/index.md) / [reference](reference.md) sections are
> for you — this page is the friendly on-ramp for everyone else.

## What this gives you

Once it's connected, your assistant works **directly inside your real Godot project**:

- create and arrange scenes and nodes,
- write and fix GDScript,
- run the game and read the errors,
- and check its own work — with every change landing on Godot's own **undo** stack, so
  you can Ctrl+Z anything it does.

You stay in Godot; the assistant works through the editor you already have open.

## What you need

- **Godot 4.4 or newer**, with your project open.
- An **AI assistant that can run commands and edit files** — for example Claude Code,
  OpenAI Codex, or OpenCode. A plain chat window can't install things for you (see
  [Not using a coding assistant?](#not-using-a-coding-assistant) below).
- That's everything — the assistant installs godot-mcp itself.

## Step 1 — Open your project in Godot

Have your Godot project open in the editor. Any project works; a brand-new empty one is
fine to start.

## Step 2 — Ask your assistant to set it up

Open your assistant **in your project's folder** and paste this:

```text
Set up godot-mcp for my Godot project so you can drive the editor.

1. Install the server: run `pip install godot-editor-mcp`. (If pip is unavailable, don't
   install anything else — `uvx godot-editor-mcp` runs it on demand and is enough.)
2. Register godot-mcp as an MCP server for yourself, launching it with the command
   `uvx godot-editor-mcp` over stdio. Use the correct MCP-config method for your client
   (for Claude Code that is: `claude mcp add godot -- uvx godot-editor-mcp`).
3. Install the Godot addon into my project: download the latest `godot_mcp_addon.zip`
   from https://github.com/hybridindie/godot-mcp/releases/latest and unzip it into my
   project folder (it adds `addons/godot_mcp/`).
4. Install the godot-mcp AI skills into your own skills directory so you know how to work
   here — they teach you to enable toolsets on your own, read the result verdicts, and
   avoid the common Godot pitfalls. Clone or download
   https://github.com/hybridindie/godot-mcp and copy the three folders under its `skills/`
   directory (godot-getting-started, godot-playtest-and-debug, godot-expert) into your
   skills directory — keep godot-expert/references/ intact. Reload your skills when done.
5. When that's done, tell me to enable the addon: in Godot, Project → Project Settings →
   Plugins → enable "Godot Editor MCP - Addon".
6. Once I confirm, verify the connection by calling `godot_health_check` and
   `godot_get_server_info`, and tell me the version it reports.

Ask me for my project folder path if you're not sure where it is.
```

## Step 3 — Enable the addon (the one click that's yours)

In Godot: **Project → Project Settings → Plugins**, and switch on **Godot Editor MCP - Addon**. A small
status dock appears at the bottom of the editor. When its dot turns **green**, the
assistant is connected and ready.

![The godot-mcp status dock: a green Connected dot, the Godot version and bridge URL, the active scene and selected node, the last undoable action, the enabled toolsets, and a recent-command log showing what the assistant has been doing.](/dock.svg)

*A green dot means connected. The **recent-command log** at the bottom shows exactly what the assistant has been doing, and the **Last action** row is undoable with Ctrl+Z.*

## Step 4 — Check it worked

Tell your assistant:

```text
Run a health check on godot-mcp and tell me whether the Godot editor is connected.
```

If it reports *connected* (and its version matches what it installed), you're set.

## Now make something

Just describe what you want, in plain language:

- *"Create a new scene with a player that moves with the arrow keys."*
- *"Add a HUD showing the player's health, top-left."*
- *"The jump feels too floaty — make it snappier."*
- *"Run the game and tell me about any errors."*
- *"Set up a main menu with Play and Quit buttons."*

The assistant turns that into editor actions; you watch them happen in Godot and undo
anything you don't like.

### What the assistant can do

| You say… | What happens in Godot |
|----------|-----------------------|
| "build / change a scene" | nodes, properties, and signals — with undo |
| "write / fix this script" | GDScript written into your project, with a parse check |
| "run it and tell me what breaks" | the game runs; errors and warnings come back |
| "test that X works" | live checks and screenshots |
| "export a build" | Web / desktop builds |

### Things worth knowing

- **It asks before destroying.** Deleting or overwriting needs your OK first; previews are free.
- **Everything is undoable.** The assistant's changes sit on the same undo stack as yours — Ctrl+Z works.
- **It can't see *your* screen** — but a vision-capable assistant can screenshot the editor or the running game to *look at* the scene. It still can't watch you, so answer its questions and keep an eye on the editor.
- **Better assistants go further.** Claude Code and Codex can run the setup and chain many steps; a small local model may need more back-and-forth.

## If something's off

| What you see | What to do |
|--------------|------------|
| "Godot bridge is not connected" | Make sure Godot is open with the addon enabled and the dock dot green. |
| The dock dot stays grey or red | Restart Godot, or toggle the plugin off and on again. |
| "unknown tool" | Ask the assistant to *"enable the toolset it needs first."* |
| The assistant can't find Godot | Tell it where your Godot app and project folder are. |
| It broke after an update | Ask the assistant to reinstall the addon from the latest release. |

Still stuck? Point the assistant at the [workflow prompts](reference-prompts.md)
(including `troubleshoot`) — they're written for exactly this.

## Not using a coding assistant?

The setup above needs an assistant that can run commands and edit files. If you only have
a **chat window** (no agent), ask a technical friend to do the [technical install](getting-started-install.md)
once — after that, any MCP-capable assistant can use it.

---

**Technical readers.** If you want the internals — or to contribute — the rest of these
docs are for you: start at [Concepts](concepts.md) or
[Under the hood](architecture/index.md), and see
[`CONTRIBUTING.md`](https://github.com/hybridindie/godot-mcp/blob/main/CONTRIBUTING.md).
