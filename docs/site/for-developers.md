---
type: index
title: "For developers"
description: "Integrate, extend, or contribute to Godot Editor MCP — architecture, setup, the tool contract, and the extension points."
created: 2026-10-18
updated: 2026-10-18
---

# For developers

**You know MCP and want the internals, a stable integration surface, or to contribute.**
This track is the technical map.

Godot Editor MCP is a generic, game-agnostic MCP server. It drives a **live Godot
editor** — the editor is the surface, reached through the addon — rather than editing
files blindly on disk.

## The shape in one picture

```text
AI client ──stdio / HTTP──▶ FastMCP server ──WebSocket──▶ Godot addon ──▶ live editor
```

- The **server** (`mcp_server/`) owns safety, preconditions, typed models, the tool
  surface, and the WebSocket listener.
- The **addon** (`godot/addons/godot_mcp/`) is the only code that touches the Godot
  Editor API. It dials out to the server and reconnects.
- The **JSON envelope** (`{id, command, params}` → `{id, ok, result, error}`) joins them.

## Set up

- **[Install the MCP server](getting-started-install.md)** — PyPI, Docker, or source.
- **[Install the Godot addon](getting-started-addon.md)** — Asset Store, copy, or the
  bundled project.
- **[Configure your MCP client](getting-started-clients.md)** — stdio or Streamable HTTP.
- **[Remote & multi-client](getting-started-openwebui.md)** — one HTTP service, several
  clients, one editor.

## Understand the contract

- **[Concepts](concepts.md)** — the mental model: editor-first, toolsets, safety classes,
  the envelope, honesty fields.
- **[Reference](reference.md)** — the readable map of the surface.
- **[Toolsets & tools](reference-toolsets.md)** — every tool and its safety class.
- **[Safety classes](reference-safety-classes.md)** — `dry_run` / `confirm` semantics.
- **[Value shapes](reference-value-shapes.md)** — how Godot types arrive as JSON.
- **[Errors & recovery](reference-errors.md)** — the stable error enum and recovery hints.
- **[Prompts & resources](reference-prompts.md)** — workflow templates and `godot://`
  snapshots.
- **[Environment variables](reference-env-vars.md)** — every server and addon knob.
- **[Tool contracts](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md)**
  — the authoritative per-tool schema (source of truth).

## Go under the hood

- **[The four-layer chain](architecture/index.md)** — where every responsibility lives.
- **[The Godot addon](architecture/addon.md)** — dial-out client, router, dock, undo.
- **[Bridge & transport](architecture/bridge.md)** — lifecycle, backoff, timeouts.
- **[The JSON envelope](architecture/envelope.md)** — correlation and error codes.
- **[Toolset gating](architecture/gating.md)** — the enabled set and `list_changed`.
- **[The safety model](architecture/safety.md)** — classes, preconditions, gates.
- **[Persistence truth](architecture/persistence.md)** — the owner chain and save verdicts.
- **[The readiness envelope](architecture/readiness.md)** — why nothing stalls silently.

## Integrate or extend

- **[Consumer integration](reference-consumers.md)** — layering game-specific agents on
  top, pinning the tool names, params, envelope, and contract version.
- **[Skills](reference-skills.md)** — the three installable AI skills.
- **[Contributing](https://github.com/hybridindie/godot-mcp/blob/main/CONTRIBUTING.md)** —
  setup, workflow, conventions, and the grounding rules.

## Stable identifiers

| Thing | Value | Change policy |
|-------|-------|---------------|
| Product name | **Godot Editor MCP** | human-facing |
| Repository | `hybridindie/godot-mcp` | stable |
| MCP server ID | `godot-mcp` | wire compatibility |
| Package / CLI | `godot-editor-mcp` | published name |
| Addon | **Godot Editor MCP - Addon** | Asset Store name |
| Tools | `godot_<toolset>_<action>` | gated by the prefix |
| Contract version | `contract_version` in `godot_get_server_info` | additive changes do not bump it |

Read the [naming note](concepts.md#naming-godot-editor-mcp) for why the product name and
the identifiers differ.

---

**Just want to make a game?** The [creator track](for-creators.md) skips all of this.
