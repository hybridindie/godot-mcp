@tool
class_name MCPScriptHandlers
extends RefCounted
## Domain handler: scripts.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_script_for_node"] = _cmd_get_script_for_node
	handlers["cmd_list_scripts"] = _cmd_list_scripts
	handlers["cmd_patch_script"] = _cmd_patch_script
	handlers["cmd_read_script"] = _cmd_read_script
	handlers["cmd_write_script"] = _cmd_write_script


# -- handlers ----------------------------------------------------------------

func _cmd_read_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _router._fail("VALIDATION_ERROR", "script_path must be a .gd file: '%s'." % path)
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	return _router._ok({"script_path": path, "content": FileAccess.get_file_as_string(path)})



func _cmd_list_scripts(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var scripts: Array = []
	_collect_gd(directory, scripts)
	scripts.sort()
	return _router._ok({"directory": directory, "scripts": scripts})



func _cmd_get_script_for_node(params: Dictionary) -> Dictionary:
	var raw := str(params.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	var node: Node
	if raw.is_empty():
		var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
		if selected.is_empty():
			return _router._fail("PRECONDITION_FAILED", "No node_path given and nothing selected.", "node_or_selection")
		node = selected[0]
	else:
		if root == null:
			return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
		if raw.begins_with("/"):
			raw = raw.substr(1)
		if raw.is_empty():
			raw = "."
		node = root.get_node_or_null(NodePath(raw))
		if node == null:
			return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params.get("node_path", "")))
	# Always report the resolved scene-relative path so the response is self-describing.
	var resolved := Inspect.relative_path(node, root) if root != null else String(node.name)
	var script: Variant = node.get_script()
	if not (script is Script) or script.resource_path.is_empty():
		return _router._ok({"node_path": resolved, "script_path": null, "content": null})
	return _router._ok({
		"node_path": resolved,
		"script_path": script.resource_path,
		"content": FileAccess.get_file_as_string(script.resource_path),
	})



func _cmd_write_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _router._fail("VALIDATION_ERROR", "script_path must end with .gd.")
	var content := str(params.get("content", ""))
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Write script %s" % path)
	ur.add_do_method(_router, "_write_file_text", path, content)
	if existed:
		ur.add_undo_method(_router, "_write_file_text", path, old)
	else:
		ur.add_undo_method(_router, "_remove_file", path)
	ur.commit_action()
	return _router._ok({"script_path": path, "created": not existed})



func _cmd_patch_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _router._fail("VALIDATION_ERROR", "script_path must end with .gd.")
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	var find := str(params.get("find", ""))
	if find.is_empty():
		return _router._fail("VALIDATION_ERROR", "'find' must be a non-empty string.")
	var content := FileAccess.get_file_as_string(path)
	var occurrences := content.count(find)
	if occurrences == 0:
		return _router._fail("VALIDATION_ERROR", "'find' text was not found in the script.")
	var patched := content.replace(find, str(params.get("replace", "")))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Patch script %s" % path)
	ur.add_do_method(_router, "_write_file_text", path, patched)
	ur.add_undo_method(_router, "_write_file_text", path, content)
	ur.commit_action()
	return _router._ok({"script_path": path, "replacements": occurrences})


func _collect_gd(directory: String, out: Array) -> void:
	var dir := DirAccess.open(directory)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := directory.path_join(name)
		if dir.current_is_dir():
			if not name.begins_with("."):
				_collect_gd(full, out)
		elif name.ends_with(".gd"):
			out.append(full)
		name = dir.get_next()
	dir.list_dir_end()


