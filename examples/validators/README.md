# Project validators

`godot_analysis_validate_project` runs project-owned rules in a headless Godot
process, so the same findings are available to an agent and to CI.

## Install

Copy a validator into your project:

```
res://.mcp/validators/<name>.gd
```

Enable the `analysis` toolset, then call `godot_analysis_validate_project`.
Built-in checks (missing autoload targets, broken scene/resource dependencies,
scripts that fail to load) run alongside your validators.

## Interface

A validator is a `@tool` script extending `RefCounted` with:

```gdscript
func validate(context: Dictionary) -> Array:
	# context: {project_dir: String, editor: bool, include_warnings: bool}
	return [
		{
			"severity": "error",   # error | warning | info
			"path": "res://...",   # optional
			"message": "...",
			# "next_call": {"tool": "...", "args": {}, "reason": "..."}  # optional
		},
	]
```

`severity: "error"` makes `valid` false. `include_warnings=false` filters
warnings from the result. A malformed return value becomes a finding rather than
being silently dropped.

`no_todos.gd` is a minimal example.
