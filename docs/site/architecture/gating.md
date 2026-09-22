---
type: index
title: "Toolset gating"
description: "Why 186 tools are gated, how the enabled set works, and what list_changed does."
created: 2026-09-19
updated: 2026-09-19
---

# Toolset gating

A large flat tool surface degrades agent tool-selection and burns context. So
the *live* surface stays small: `core` + `inspection` are exposed by default
(18 tools), and 27 further toolsets are **gated off** until the agent enables
them.

## The enabled set

`enable_toolset` / `disable_toolset` write into a **single server-global
enabled set** (issue #364). godot-mcp is a single-user, locally-run server —
per-session isolation was removed because it was dead code on the sessionless
MCP `2026-07-28` protocol (a fresh `session_id` per call made it useless) and
violated the no-server-initiated-hook rule. Consequences, which are features:

- A grant issued on one connection **persists to a fresh connection** against
  the same server process — a reconnect between enable and mutate keeps the
  grant.
- All clients see the same surface. There is no per-session isolation to reason
  about.
- The set is seeded at startup from `GODOT_MCP_DEFAULT_TOOLSETS` (`all` or a
  comma-separated list; unknown names are logged and ignored). The agent-facing
  protocol text derives its wording from the effective default so it never
  claims "everything is hidden" when the operator seeded more (#425).

## `tools/list_changed`

Since 2026.09.17 (#491/#485), `enable_toolset`/`disable_toolset` emit
`notifications/tools/list_changed` after mutating the set. Clients that cache
the tool list at session start refresh on the notification. The send is
fire-and-forget by design — the toggle already succeeded, so a delivery failure
must not fail the tool call — but it is logged, never swallowed silently.

The typed tools remain authoritative either way: calling a gated tool whose
toolset is disabled fails with a structured gating error, and
`_ensure_or_return_error`-style client helpers re-enable idempotently.

## Why the gate is worth its friction

1. **Tool selection sharpness.** With 186 tools exposed, models confuse
   similar tools and waste calls. The default 18-tool surface fits in context
   with room to reason.
2. **Safety surface minimization.** Destructive tools (`delete_node`,
   `reload_scene`, `close_scene`, bus removers, file deleters) are *invisible*
   until the agent deliberately asks for a toolset containing them.
3. **Version gating** rides the same flag: `scene_edit`, `input_map`,
   `tilemap`, `scene_3d` require Godot 4.4+ and refuse to enable on older
   editors with a structured error naming the requirement.

## The toolsets

| Domain | Toolsets |
|--------|----------|
| Scene building | `scene_edit` · `composite` (macro round-trips) · `scene_3d` · `theme_ui` · `tilemap` · `particles` · `navigation` · `physics` · `animation` · `audio` · `shader` · `visual_shader` |
| Code & data | `scripts` · `resources_edit` · `project` · `project_scaffold` |
| Run & verify | `runtime` · `input` · `testing` · `debugger` · `profiling` |
| Bulk & ship | `batch` · `analysis` · `export` · `asset_import` · `editor` |

Plus always-on `core` (diagnostics, toolset management, `godot_undo`,
`godot_debug_workflow`) and `inspection`.

The full per-toolset table (with tool names and counts) lives in the
[toolsets reference](../reference-toolsets.md); the authoritative per-tool spec
is [`docs/tool-contracts.md`](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md).

## Design guardrails

- **New categories register gated off** — added to `TOOLSETS`, never to
  `DEFAULT_ENABLED`. Growth of the catalog does not grow the default surface.
- **Fewer, richer tools over many micro-tools.** Create-with-config
  (`create_node(…, properties?, script?)`) and batch setters replace
  one-tool-per-field. One tool per noun with a few clear verbs.
- **Never merge across safety classes.** Folding `delete` into a fat `node`
  tool would bury the `confirm` gate; the class split is deliberate.
- **Never a single `do(action, params)` dispatcher** — that discards the
  per-tool schemas and descriptions that guide the agent.