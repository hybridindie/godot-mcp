@tool
extends RefCounted
## Example project validator (#758).
##
## Copy this file to `res://.mcp/validators/` in your project (and enable the
## `analysis` toolset). `godot_analysis_validate_project` discovers it and runs
## `validate(context)`; return an Array of
## `{severity, path, message, next_call?}` dictionaries.

func validate(_context: Dictionary) -> Array:
	var findings: Array = []
	for path in _scenes("res://"):
		if FileAccess.get_file_as_string(path).contains('name="TODO"'):
			findings.append({
				"severity": "warning",
				"path": path,
				"message": "Scene contains a node named TODO.",
			})
	return findings


func _scenes(dir: String) -> Array:
	var out: Array = []
	var handle := DirAccess.open(dir)
	if handle == null:
		return out
	handle.list_dir_begin()
	var name := handle.get_next()
	while name != "":
		if name.begins_with("."):
			name = handle.get_next()
			continue
		var full := dir.path_join(name)
		if handle.current_is_dir():
			out.append_array(_scenes(full))
		elif name.ends_with(".tscn"):
			out.append(full)
		name = handle.get_next()
	handle.list_dir_end()
	return out
