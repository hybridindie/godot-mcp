# Project tools

`godot_project_scan_tools` turns a project's own operations into MCP tools, so an
agent calls `spawn_wave` instead of reconstructing it from node and property
edits.

## Install

1. Copy a `@tool` script into your project (anywhere outside `res://addons/`):

   ```
   res://scripts/waves.gd
   ```

2. Enable the `project` toolset:

   ```
   godot_enable_toolset(category="project")
   ```

3. Scan:

   ```
   godot_project_scan_tools()
   ```

Each annotated function becomes `godot_project_<script stem>_<function>` — for
the example above, `godot_project_waves_spawn_wave`. Re-scan after adding or
removing annotations; the previous set is replaced.

## Annotation

A function is a project tool when a `## @mcp_tool` doc tag sits directly above it:

```gdscript
## Spawn a wave of enemies.
## @mcp_tool safety=mutating
func spawn_wave(count: int, kind: String = "enemy") -> Dictionary:
```

- The `##` lines above the tag become the tool description.
- `safety=read_only|mutating|destructive` (default `mutating`) adds `dry_run`
  for mutating tools and `confirm=True` for destructive ones. The gate is
  enforced server-side, before the bridge.
- Parameters must be statically typed: `int`, `float`, `bool`,
  `String`/`StringName`/`NodePath`, `Vector2`/`Vector3`/`Color`, script enums, and
  `Array[T]`. Anything else is rejected with a reason and a line number — a
  rejection never fails the scan.
- Optional parameters (`= default`) must be trailing.

`waves.gd` is a minimal example.

## Execution and undo

The addon calls `load(script).new()` then `callv`, so project tool scripts should
extend `RefCounted`. **Each function owns its undo behavior** — the addon does
not wrap project-tool calls in `EditorUndoRedoManager`. Make a `mutating` tool
undoable itself, or let the result's receipt record how to reverse it.
