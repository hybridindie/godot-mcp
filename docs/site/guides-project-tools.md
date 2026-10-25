---
type: index
title: "Project-defined tools"
description: "Expose a project's own operations as godot_project_* MCP tools — annotate, scan, call, with the same safety classes as the built-ins."
created: 2026-10-25
updated: 2026-10-25
---

# Project-defined tools

Every game has operations that are not generic node edits: spawn a wave, add an
item to the loot table, register a level. Instead of asking the assistant to
reconstruct them from primitive edits, a project can expose them as **its own
tools**.

They live in the gated `project` toolset and behave like any other tool: typed
input schema, a safety class, `dry_run`/`confirm`, toolset gating, and
`notifications/tools/list_changed` when the surface changes.

## Quick start

**1. Annotate a typed function** in an `@tool` script (outside `res://addons/`):

```gdscript
@tool
extends RefCounted

enum Kind { ENEMY, BOSS }

## Spawn a wave of enemies.
## @mcp_tool safety=mutating
func spawn_wave(count: int, kind: Kind = Kind.ENEMY) -> Dictionary:
	return {"spawned": count, "boss": kind == Kind.BOSS}
```

**2. Enable the toolset and scan:**

```
godot_enable_toolset(category="project")
godot_project_scan_tools()
```

**3. Call it by name:** `godot_project_waves_spawn_wave(count=3)`.

The tool name is `godot_project_<script stem>_<function>` — `waves.gd` +
`spawn_wave` becomes `godot_project_waves_spawn_wave`.

## The annotation

- The `## @mcp_tool` tag must sit directly above the `func`; a blank line or
  another statement detaches it.
- The `##` lines above the tag become the tool description.
- `safety=` is `read_only`, `mutating` (the default), or `destructive`.
- Every parameter must be statically typed — the schema is derived from the type.

### Supported types

| GDScript type | JSON Schema |
|---------------|-------------|
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `String`, `StringName`, `NodePath` | `string` |
| `Vector2` / `Vector3` | object `{x, y}` / `{x, y, z}` |
| `Color` | object `{r, g, b, a}` |
| a script `enum` | string enum of the member names (converted back to the int value on call) |
| `Array[T]` | array of the element's schema |

The scanner **rejects** — with the reason and line number, as partial success,
never as a failed scan — an untyped parameter, `Dictionary`, a bare `Array`, an
unsupported type, and a non-default parameter after a default one. Optional
parameters (`= default`) carry their default and must be trailing.

## Safety classes

| Tag | Extra parameters | Gate |
|-----|------------------|------|
| `read_only` | — | none |
| `mutating` | `dry_run` | `dry_run=True` previews without changing anything |
| `destructive` | `dry_run`, `confirm` | requires `confirm=True` |

All of it is enforced **server-side before any bridge call**, exactly like the
built-in tools.

## Registration lifecycle

- `godot_project_scan_tools()` **replaces** the previous set: removing an
  annotation removes the tool.
- A scan publishes `notifications/tools/list_changed`; subscribed clients refresh
  their registry.
- Re-scan is explicit today — automatic refresh on filesystem change is tracked
  as [#802](https://github.com/hybridindie/godot-mcp/issues/802).
- The tools are gated with the `project` toolset (off by default), so the surface
  stays small until a project opts in.

## Execution and undo

The addon loads the script, instantiates it, and calls the function with the named
arguments. **Each function owns its undo behavior** — the addon does not wrap
project-tool calls in `EditorUndoRedoManager`. Make a `mutating` tool undoable
itself, or report how to reverse it. A timeout on the shared call is flagged
`may_have_applied`, because the editor drains commands serially.

Scripts should extend `RefCounted`.

## Example and contract

- [`examples/project_tools/waves.gd`](https://github.com/hybridindie/godot-mcp/blob/main/examples/project_tools/waves.gd)
  — a read-only, a mutating, and a destructive tool.
- [`examples/project_tools/README.md`](https://github.com/hybridindie/godot-mcp/blob/main/examples/project_tools/README.md)
  — install and annotated reference.
- [Tool contracts](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md)
  — field-level detail for `godot_project_scan_tools` and the generated tools.
