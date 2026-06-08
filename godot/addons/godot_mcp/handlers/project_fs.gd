@tool
class_name MCPProjectFSHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: project fs.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter





func _file_contains(path: String, needle: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	if file.get_length() > 2_000_000:  # skip large/binary files
		file.close()
		return false
	var text := file.get_as_text()
	file.close()
	return text.contains(needle)


func _search(dir_path: String, name_glob: String, content: String, max_results: int, out: Array) -> bool:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return false
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				if _search(full, name_glob, content, max_results, out):
					dir.list_dir_end()
					return true
			elif (name_glob.is_empty() or name.match(name_glob)) \
					and (content.is_empty() or _file_contains(full, content)):
				out.append(full)
				if out.size() >= max_results:
					dir.list_dir_end()
					return true
		name = dir.get_next()
	dir.list_dir_end()
	return false


func _fs_node(dir_path: String, max_depth: int) -> Dictionary:
	var node: Dictionary = {
		"name": ("res://" if dir_path == "res://" else dir_path.trim_suffix("/").get_file()),
		"path": dir_path,
		"type": "directory",
		"children": [],
	}
	if max_depth == 0:
		return node
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return node
	var child_depth: int = (max_depth - 1) if max_depth > 0 else -1
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				node["children"].append(_fs_node(full, child_depth))
			else:
				node["children"].append({"name": name, "path": full, "type": "file"})
		name = dir.get_next()
	dir.list_dir_end()
	return node


## Recursively collect files matching name_glob and/or content; returns true if the
## result was truncated at max_results.
func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_filesystem_tree"] = _cmd_get_filesystem_tree
	handlers["cmd_get_setting"] = _cmd_get_setting
	handlers["cmd_path_to_uid"] = _cmd_path_to_uid
	handlers["cmd_search_files"] = _cmd_search_files
	handlers["cmd_set_setting"] = _cmd_set_setting
	handlers["cmd_uid_to_path"] = _cmd_uid_to_path


# -- handlers ----------------------------------------------------------------

func _cmd_get_filesystem_tree(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var max_depth := int(params.get("max_depth", -1))
	return _router._ok({"tree": _fs_node(directory, max_depth)})



func _cmd_search_files(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var name_glob := str(params.get("name_glob", ""))
	var content := str(params.get("content", ""))
	var max_results := int(params.get("max_results", 200))
	var matches: Array = []
	var truncated := _search(directory, name_glob, content, max_results, matches)
	return _router._ok({"matches": matches, "truncated": truncated})



func _cmd_get_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if not ProjectSettings.has_setting(setting):
		return _router._ok({"name": setting, "value": null, "exists": false})
	return _router._ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"exists": true,
	})



func _cmd_set_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if setting.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var raw: Variant = params.get("value")
	var value: Variant = raw
	if ProjectSettings.has_setting(setting):
		# Coerce to the setting's existing type so e.g. a vector dict becomes a Vector2.
		value = Coerce.from_json(raw, typeof(ProjectSettings.get_setting(setting)))
	ProjectSettings.set_setting(setting, value)
	ProjectSettings.save()
	return _router._ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"set": true,
	})



func _cmd_path_to_uid(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var id := ResourceLoader.get_resource_uid(path)
	if id == -1:
		return _router._fail("RESOURCE_NOT_FOUND", "No UID for '%s'." % path)
	return _router._ok({"path": path, "uid": ResourceUID.id_to_text(id)})



func _cmd_uid_to_path(params: Dictionary) -> Dictionary:
	var uid := str(params.get("uid", ""))
	var id := ResourceUID.text_to_id(uid)
	if id == -1 or not ResourceUID.has_id(id):
		return _router._fail("RESOURCE_NOT_FOUND", "Unknown UID '%s'." % uid)
	return _router._ok({"uid": uid, "path": ResourceUID.get_id_path(id)})


