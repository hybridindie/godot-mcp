---
type: index
title: "Comparison with other Godot AI tools"
description: "An honest side-by-side of Godot Editor MCP against the other MCP servers that drive a live Godot editor — including where it is not ahead."
created: 2026-11-07
updated: 2026-11-07
---

# Comparison with other Godot AI tools

There are now several MCP servers that drive a live Godot editor. They are all
worth trying, and they optimize for different things. This page is an honest
side-by-side — including the places where this project is **not** ahead.

Capability facts were checked against each project's README/docs on
**2026-11-06**. "Not documented" means it could not be confirmed from public
docs; it does **not** mean the feature is absent. Star and download figures
move — re-check them before quoting this page.

| Capability | **Godot Editor MCP** | Godot AI (hi-godot) | tomyud1/godot-mcp | IvanMurzak/Godot-MCP | KeeVeeG/godot-mcp |
|---|---|---|---|---|---|
| Drives the **live** editor | ✅ via addon | ✅ | ✅ | ✅ | ✅ |
| **Undo** | ✅ native — Godot's undo stack, Ctrl+Z works | not documented | ⚠️ app-level `mcp_undo`; *Ctrl+Z does not reach AI changes* | ✅ native ("undoable, Ctrl+Z") | ✅ native |
| **Pre-mutation preview** (`dry_run`) | ✅ (safety classes) | not documented | not documented | ✅ | not documented |
| **Post-mutation ground truth** (`persisted`, `undoable`, `aborted_at`, `rescan_pending`) | ✅ incl. reason tokens (`node_not_owned`, `instanced_child_not_editable`) | not documented | not documented | partial — all-or-nothing batches | not documented |
| **Gated tool surface** (load only what a task needs) | ✅ core + 28 toggleable toolsets | ✅ tool domains | not documented | not documented | ❌ 300+ always available |
| **Versioned compatibility contract** | ✅ `contract_version` + `min_compatible_contract`, contract-tested | not documented | not documented | not documented | not documented |
| **Project-defined tools** (extension point) | ✅ `## @mcp_tool` → typed, safety-classed `godot_project_*` tools | not documented | not documented | ✅ extensions + RQL (cloud-tied) | not documented |
| **Ships Godot skills** | ✅ 3 — incl. `godot-expert` | not documented | not documented | ✅ `godot-rql` skill | not documented |
| **Multiple clients over one editor** | ✅ long-lived HTTP service, Docker, self-host | ✅ (multi-*instance* — many editors) | ✅ | ✅ | ✅ |
| **No telemetry** | ✅ | ⚠️ anonymous telemetry, opt-out | ✅ | ✅ (self-host) | ✅ |
| **Client lock-in** | none — any MCP client, plain config | ⚠️ dock auto-configures 26 clients, rewrites/redirects your config | none | ⚠️ project-pinned cloud route by default | none |
| **Language / distribution** | Python + GDScript; PyPI, Docker, Asset Store, `llms.txt` | Python + GDScript; Asset Store, Snap, releases, Discord | GDScript; Asset Store | C#; Asset Store + cloud + NuGet | TypeScript; GitHub |
| **License** | MIT | MIT | MIT | Apache-2.0 | MIT |
| **Traction (Nov 2026)** | 51★ · ~2.4k PyPI dl/mo · 10 releases/5mo | 3,412★ · 21k MAU installs · 30M tool calls/3mo | 451★ | 325★ | ~31★ |

## Where this project leads

- **Post-mutation ground truth.** No other project checked returns
  machine-readable answers to *"did this actually land, will a save keep it,
  and can Ctrl+Z actually reverse it?"* — including warning that a batch above
  20 nodes is *not* undoable. For an unattended agent, "looks done" versus "is
  done" is the difference between progress and a silently broken scene. See
  [Persistence truth](architecture/persistence.md).
- **A versioned, game-agnostic contract.** A stable surface you can build
  *on*, where additive changes never bump the version and contract tests catch
  drift. See [The compatibility contract](reference-contract.md).
- **A local, typed extension point.** `## @mcp_tool` on a typed GDScript
  function becomes a first-class, safety-classed project tool that runs entirely
  in your editor — your game's vocabulary, without a cloud or a fork. See
  [Project-defined tools](guides-project-tools.md).
- **Skills ship with it.** The platform bundles Godot expertise, not just tools.
  See [Skills](reference-skills.md).
- **No telemetry, no cloud, no lock-in.** Self-hostable, any MCP client, MIT.

## Where it does not lead

- **Traction.** 51★ against 3,412, and ~2.4k PyPI downloads/month against 21k
  monthly active installs. This project is not competing on visibility today.
- **Tool count.** 208 against 300+ (KeeVee). The tool count is deliberately not
  a race: a small gated surface selects better and burns less context than a
  sprawl.
- **Undo alone is not the claim.** Godot AI, IvanMurzak, and KeeVee all have
  undo, and `dry_run` exists elsewhere too. The claim is *undo plus ground
  truth together*.
- **Client-config polish, C# coverage, multi-editor, signed releases, Discord.**
  Godot AI is ahead on several of these. Better to say so than to pad the table.

## The adjacent market

Unity shipped an **official** MCP server in August 2026, Epic shipped one for
Unreal, and `ahujasid/blender-mcp` sits around 26k stars. AI-driven editing is a
maturing mainstream category; the Godot side of it is where this project lives.

---

**Building on it?** Start with [Consumer integration](reference-consumers.md) and
[For developers](for-developers.md).
