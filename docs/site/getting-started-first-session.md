---
type: index
title: "Your first session"
description: "Install the skill, then drive a real Godot project from your AI assistant — the orient → enable → preview → act → verify rhythm."
created: 2026-09-19
updated: 2026-10-16
---

# Your first session

godot-mcp is driven **through an AI assistant**, not by typing tool names. So the single
most useful thing you can do first is **install the skill** — a small bundle of knowledge
your assistant loads automatically. It teaches it to:

- check the bridge and version before it starts,
- **enable the toolset it needs, by itself** (you never manage gates), and
- read the "what actually happened" fields and avoid the Godot pitfalls that trip agents up.

→ **[Install the skills](reference-skills.md)** (copy the `skills/` folders into your
client), then restart your assistant. From then on it just knows how to work in Godot.

With the skill in place you talk in plain language and supervise in Godot. The rhythm is
always the same: **orient → enable → preview → act → verify.**

::: warning No skill installed?
The workflow degrades gracefully without it, but the assistant won't know to enable
toolsets on its own or to read the honesty fields — you'll be prompting it about
"unknown tool" errors and stale-save verdicts yourself. Install the skill.
:::

## 1. Orient — ask who's connected

You: *"Check that Godot is connected and tell me what's available."*

The assistant confirms the editor is reachable and tells you what it can do. If it says the
bridge isn't connected, open Godot with the [addon enabled](getting-started-addon.md), check
the status dock (bottom panel), and ask again — its report usually names the fix.

## 2. Enable what you need — the assistant handles it

Ask for anything that needs a gated toolset and the assistant turns it on itself — the part
the getting-started skill teaches, so you don't have to think about it.

You: *"Add a Player node to the main scene."*

If your assistant instead stalls on an "unknown tool" error, it's missing the skill (or
hasn't enabled the toolset) — prompt it: *"enable the toolset you need first"*, or
[install the skill](reference-skills.md).

## 3. Inspect before mutating — the assistant reads, then edits

You: *"What's in the scene right now?"*

The assistant reads the scene tree, your current selection, and the project setup
(autoloads, input actions, main scene). Node paths come back scene-relative
(`"."`, `"Player/Weapon"`) in exactly the form the editing tools expect — and you can see
the same thing live in Godot's Scene dock.

## 4. Preview, then act — you approve, the assistant mutates

You: *"Create the Player node — preview it first."*

Ask for a preview and the assistant shows what *would* happen, running the same checks the
real run will — including whether a save would keep it — before anything changes. When it
goes ahead, the change lands in **your** editor: watch it appear in the Scene dock, and
press **Ctrl+Z** to undo it. Every assistant change is on the editor undo stack — as
revertible as your own edits.

## 5. Verify — ask the assistant to prove it worked

You: *"Check the script parses and the scene runs without errors."*

A clean parse is **not** full verification — runtime mistakes only show up when the game
actually runs. Ask for the verdict, not just the action: *"does it run clean?"* is a
different question from *"did you save it?"*

## Reading the results the assistant reports back

::: info Under the hood
These fields are the server's **honesty contract** — what a save will *really* keep, what a
batch actually ran, whether a check raced a rescan. See
[Persistence truth](architecture/persistence.md) for how they're produced.
:::

The assistant's results carry **honesty fields** that read as ground truth — check them (or
ask the assistant to explain them):

- `persisted: true` → the save will keep the change.
- `persisted: false, reason: instanced_child_not_editable` → the edit shows in the editor
  but **won't be saved**; act on the hint (ask your assistant to enable Editable Children on
  the instanced scene, or to target a node the scene owns).
- `rescan_pending: true` on a parse check → the editor's file scan hadn't flushed; have the
  assistant re-check once before "fixing" correct code.
- `aborted_at` on a batch → trailing commands did **not** run.

A well-behaved assistant reads these and acts; ask it to when it doesn't.

## When something fails

| What you see | What it means | What to tell the assistant |
|--------------|---------------|----------------------------|
| "unknown tool" | the toolset isn't enabled | "enable the toolset first" |
| a "no scene open" precondition | nothing is open to edit | "open or create a scene" |
| a destructive action asks to confirm | it needs your OK first | review it, then "confirm and retry" |
| "Godot is not connected" | the editor isn't reachable | open Godot + addon; check the status dock |
| a typo'd key or path is rejected | a "did you mean…?" is offered | "use the suggested key" |

The assistant's own report (and the `troubleshoot` prompt) usually names the fix.

## Making it smoother

- **Reach for prompts.** The server's [workflow prompts](reference-prompts.md) are
  step-numbered recipes the assistant can follow for a whole task — a skill points it at the
  right one.
- **Start from an example.** The two games under [examples](guides-examples.md) give the
  assistant a real project to work against.

Next: [Build a scene](guides-build-scene.md) walks the full loop, or
[Play-test & debug](guides-playtest-debug.md) starts from the runtime side.
