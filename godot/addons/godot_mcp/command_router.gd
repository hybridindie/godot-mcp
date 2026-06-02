@tool
class_name MCPCommandRouter
extends RefCounted
## Routes incoming command envelopes to cmd_* handlers (issues #3, #5).
##
## Pure dispatch + structured errors; every outcome is a JSON-safe response
## envelope — { id, ok, result } or { id, ok:false, error, hint[, required] } —
## never a raw error or crash (see .claude/rules/error-handling.md).
##
## Handlers receive the params dict and return a response *body* (without id) via
## the _ok / _fail builders; handle() stamps the id. Read-only inspection
## handlers (#5) read editor state through EditorInterface; safety/preconditions
## are owned by the MCP server, except the local guards needed to return a
## structured error instead of crashing.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")

var _handlers: Dictionary = {}


func _init() -> void:
	# Wire command strings are the cmd_<verb>_<noun> handler names (the matching MCP
	# tool drops the cmd_ prefix); see docs/architecture.md.
	_handlers["cmd_ping"] = _cmd_ping
	_handlers["cmd_get_project_info"] = _cmd_get_project_info
	_handlers["cmd_get_active_scene"] = _cmd_get_active_scene
	_handlers["cmd_get_scene_tree"] = _cmd_get_scene_tree
	_handlers["cmd_get_selected_node"] = _cmd_get_selected_node
	_handlers["cmd_get_node_properties"] = _cmd_get_node_properties
	# Mutations (issue #6) — all UndoRedo-wrapped via EditorUndoRedoManager.
	_handlers["cmd_create_node"] = _cmd_create_node
	_handlers["cmd_rename_node"] = _cmd_rename_node
	_handlers["cmd_set_node_property"] = _cmd_set_node_property
	_handlers["cmd_delete_node"] = _cmd_delete_node
	_handlers["cmd_attach_script"] = _cmd_attach_script
	_handlers["cmd_connect_signal"] = _cmd_connect_signal
	_handlers["cmd_save_scene"] = _cmd_save_scene
	_handlers["cmd_create_scene"] = _cmd_create_scene
	# Script read/patch (issue #10).
	_handlers["cmd_read_script"] = _cmd_read_script
	_handlers["cmd_list_scripts"] = _cmd_list_scripts
	_handlers["cmd_get_script_for_node"] = _cmd_get_script_for_node
	_handlers["cmd_write_script"] = _cmd_write_script
	_handlers["cmd_patch_script"] = _cmd_patch_script
	# Node parity (issue #31) — all UndoRedo-wrapped.
	_handlers["cmd_duplicate_node"] = _cmd_duplicate_node
	_handlers["cmd_move_node"] = _cmd_move_node
	_handlers["cmd_add_to_group"] = _cmd_add_to_group
	_handlers["cmd_remove_from_group"] = _cmd_remove_from_group
	_handlers["cmd_list_signal_connections"] = _cmd_list_signal_connections
	_handlers["cmd_disconnect_signal"] = _cmd_disconnect_signal
	# Resource files + autoloads (issue #34).
	_handlers["cmd_read_resource"] = _cmd_read_resource
	_handlers["cmd_create_resource"] = _cmd_create_resource
	_handlers["cmd_set_resource_property"] = _cmd_set_resource_property
	_handlers["cmd_register_autoload"] = _cmd_register_autoload
	_handlers["cmd_unregister_autoload"] = _cmd_unregister_autoload
	# Project & filesystem (issue #32).
	_handlers["cmd_get_filesystem_tree"] = _cmd_get_filesystem_tree
	_handlers["cmd_search_files"] = _cmd_search_files
	_handlers["cmd_get_setting"] = _cmd_get_setting
	_handlers["cmd_set_setting"] = _cmd_set_setting
	_handlers["cmd_path_to_uid"] = _cmd_path_to_uid
	_handlers["cmd_uid_to_path"] = _cmd_uid_to_path
	# Editor screenshots (issue #33).
	_handlers["cmd_capture_editor_screenshot"] = _cmd_capture_editor_screenshot


## Dispatch one envelope ({ id, command, params }) and return a response envelope.
func handle(envelope: Dictionary) -> Dictionary:
	var body := _route(envelope)
	body["id"] = str(envelope.get("id", ""))
	return body


func has_command(command: String) -> bool:
	return _handlers.has(command)


func _route(envelope: Dictionary) -> Dictionary:
	if not envelope.has("command"):
		return _fail("VALIDATION_ERROR", "Envelope is missing 'command'.")
	var command := str(envelope["command"])
	if not _handlers.has(command):
		return _fail("VALIDATION_ERROR", "Unknown command '%s'." % command)
	var raw_params: Variant = envelope.get("params", {})
	if typeof(raw_params) != TYPE_DICTIONARY:
		return _fail("VALIDATION_ERROR", "'params' must be an object.")
	var handler: Callable = _handlers[command]
	return handler.call(raw_params as Dictionary)


# --- handlers --------------------------------------------------------------

func _cmd_ping(_params: Dictionary) -> Dictionary:
	return _ok({"pong": true})


func _cmd_get_project_info(_params: Dictionary) -> Dictionary:
	return _ok({
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"godot_version": Engine.get_version_info().get("string", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"project_path": ProjectSettings.globalize_path("res://"),
		"autoloads": _autoloads(),
		"input_actions": _input_actions(),
	})


func _cmd_get_active_scene(_params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _ok({"is_open": false, "path": null, "name": null})
	return _ok({"is_open": true, "path": root.scene_file_path, "name": _scene_name(root)})


func _cmd_get_scene_tree(params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _ok({"tree": null})
	var max_depth := int(params.get("max_depth", -1))
	return _ok({"tree": Inspect.serialize_tree(root, max_depth)})


func _cmd_get_selected_node(_params: Dictionary) -> Dictionary:
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.is_empty():
		return _ok({"selected": null})
	var root: Node = EditorInterface.get_edited_scene_root()
	return _ok({"selected": Inspect.node_info(selected[0], root if root != null else selected[0])})


func _cmd_get_node_properties(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node: Node = root.get_node_or_null(NodePath(str(params["node_path"])))
	if node == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	return _ok(Inspect.node_info(node, root))


# --- mutation handlers (issue #6) ------------------------------------------

func _cmd_create_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_type := str(params.get("node_type", ""))
	if not ClassDB.class_exists(node_type) or not ClassDB.can_instantiate(node_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable node type '%s'." % node_type)
	var parent: Node = root.get_node_or_null(NodePath(str(params.get("parent_path", "."))))
	if parent == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params.get("parent_path")))

	var node: Node = ClassDB.instantiate(node_type)
	node.name = str(params.get("name", node_type))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create %s" % node.name)
	ur.add_do_method(parent, "add_child", node)
	ur.add_do_method(node, "set_owner", root)
	ur.add_do_reference(node)
	ur.add_undo_method(parent, "remove_child", node)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(node, root), "created": true})


func _cmd_rename_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var old_name := String(node.name)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Rename %s" % old_name)
	ur.add_do_property(node, "name", str(params.get("new_name", old_name)))
	ur.add_undo_property(node, "name", old_name)
	ur.commit_action()
	return _ok({
		"node_path": Inspect.relative_path(node, EditorInterface.get_edited_scene_root()),
		"old_name": old_name,
		"new_name": String(node.name),
		"renamed": true,
	})


func _cmd_set_node_property(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var property := str(params.get("property", ""))
	var prop_type := _property_type(node, property)
	if prop_type == -1:
		return _fail("VALIDATION_ERROR", "Node has no property '%s'." % property)

	var old_value: Variant = node.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [String(node.name), property])
	ur.add_do_property(node, property, new_value)
	ur.add_undo_property(node, property, old_value)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"property": property,
		"value": Coerce.to_json(node.get(property)),
		"set": true,
	})


func _cmd_delete_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if node == root:
		return _fail("VALIDATION_ERROR", "Cannot delete the scene root.")
	# Server enforces the safety class; the addon honors the confirm flag too.
	if not bool(params.get("confirm", false)):
		return _fail("PRECONDITION_FAILED", "Deleting a node requires confirm=true.", "confirm")

	var parent := node.get_parent()
	var index := node.get_index()  # restore at the same sibling position on undo
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Delete %s" % node.name)
	ur.add_do_method(parent, "remove_child", node)
	ur.add_undo_method(parent, "add_child", node)
	ur.add_undo_method(parent, "move_child", node, index)
	ur.add_undo_method(node, "set_owner", root)
	ur.add_undo_reference(node)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "deleted": true})


func _cmd_attach_script(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var script_path := str(params.get("script_path", ""))
	if not ResourceLoader.exists(script_path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'. Create it first." % script_path)
	var script: Variant = load(script_path)
	if not (script is Script):
		return _fail("VALIDATION_ERROR", "'%s' is not a script resource." % script_path)

	var old_script: Variant = node.get_script()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Attach script to %s" % node.name)
	ur.add_do_method(node, "set_script", script)
	ur.add_undo_method(node, "set_script", old_script)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "script_path": script_path, "attached": true})


func _cmd_connect_signal(params: Dictionary) -> Dictionary:
	var source_found := _resolve(params.get("source_path", ""))
	if not source_found["ok"]:
		return source_found
	var target_found := _resolve(params.get("target_path", ""))
	if not target_found["ok"]:
		return target_found
	var source: Node = source_found["node"]
	var target: Node = target_found["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _fail("VALIDATION_ERROR", "Source has no signal '%s'." % signal_name)
	if not target.has_method(method_name):
		return _fail("VALIDATION_ERROR", "Target has no method '%s'." % method_name)
	var callable := Callable(target, method_name)
	if source.is_connected(signal_name, callable):
		return _fail("VALIDATION_ERROR", "Signal '%s' is already connected to that method." % signal_name)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Connect %s" % signal_name)
	# CONNECT_PERSIST so the connection is saved into the scene file.
	ur.add_do_method(source, "connect", signal_name, callable, Object.CONNECT_PERSIST)
	ur.add_undo_method(source, "disconnect", signal_name, callable)
	ur.commit_action()
	return _ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"connected": true,
	})


func _cmd_save_scene(_params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	if root.scene_file_path.is_empty():
		return _fail("PRECONDITION_FAILED", "Scene has no path yet; create it with a path first.", "scene_path")
	var err := EditorInterface.save_scene()
	if err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save scene (error %d)." % err)
	return _ok({"path": root.scene_file_path, "saved": true})


func _cmd_create_scene(params: Dictionary) -> Dictionary:
	var root_type := str(params.get("root_type", ""))
	var scene_path := str(params.get("scene_path", ""))
	if not ClassDB.class_exists(root_type) or not ClassDB.can_instantiate(root_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable root type '%s'." % root_type)
	if not scene_path.ends_with(".tscn") and not scene_path.ends_with(".scn"):
		return _fail("VALIDATION_ERROR", "scene_path must end with .tscn or .scn.")

	var root: Node = ClassDB.instantiate(root_type)
	root.name = scene_path.get_file().get_basename()
	var packed := PackedScene.new()
	var pack_err := packed.pack(root)
	root.free()
	if pack_err != OK:
		return _fail("INTERNAL_ERROR", "Failed to pack scene (error %d)." % pack_err)
	var save_err := ResourceSaver.save(packed, scene_path)
	if save_err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save scene to '%s' (error %d)." % [scene_path, save_err])
	# Creating a file isn't an UndoRedo-tracked tree edit; open it for editing.
	EditorInterface.open_scene_from_path(scene_path)
	return _ok({"scene_path": scene_path, "root_type": root_type, "created": true})


# --- script handlers (issue #10) -------------------------------------------

func _cmd_read_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must be a .gd file: '%s'." % path)
	if not FileAccess.file_exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	return _ok({"script_path": path, "content": FileAccess.get_file_as_string(path)})


func _cmd_list_scripts(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var scripts: Array = []
	_collect_gd(directory, scripts)
	scripts.sort()
	return _ok({"directory": directory, "scripts": scripts})


func _cmd_get_script_for_node(params: Dictionary) -> Dictionary:
	var raw := str(params.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	var node: Node
	if raw.is_empty():
		var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
		if selected.is_empty():
			return _fail("PRECONDITION_FAILED", "No node_path given and nothing selected.", "node_or_selection")
		node = selected[0]
	else:
		if root == null:
			return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
		node = root.get_node_or_null(NodePath(raw))
		if node == null:
			return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % raw)
	# Always report the resolved scene-relative path so the response is self-describing.
	var resolved := Inspect.relative_path(node, root) if root != null else String(node.name)
	var script: Variant = node.get_script()
	if not (script is Script) or script.resource_path.is_empty():
		return _ok({"node_path": resolved, "script_path": null, "content": null})
	return _ok({
		"node_path": resolved,
		"script_path": script.resource_path,
		"content": FileAccess.get_file_as_string(script.resource_path),
	})


func _cmd_write_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must end with .gd.")
	var content := str(params.get("content", ""))
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Write script %s" % path)
	ur.add_do_method(self, "_write_file_text", path, content)
	if existed:
		ur.add_undo_method(self, "_write_file_text", path, old)
	else:
		ur.add_undo_method(self, "_remove_file", path)
	ur.commit_action()
	return _ok({"script_path": path, "created": not existed})


func _cmd_patch_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must end with .gd.")
	if not FileAccess.file_exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	var find := str(params.get("find", ""))
	if find.is_empty():
		return _fail("VALIDATION_ERROR", "'find' must be a non-empty string.")
	var content := FileAccess.get_file_as_string(path)
	var occurrences := content.count(find)
	if occurrences == 0:
		return _fail("VALIDATION_ERROR", "'find' text was not found in the script.")
	var patched := content.replace(find, str(params.get("replace", "")))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Patch script %s" % path)
	ur.add_do_method(self, "_write_file_text", path, patched)
	ur.add_undo_method(self, "_write_file_text", path, content)
	ur.commit_action()
	return _ok({"script_path": path, "replacements": occurrences})


## Collect .gd files recursively under a res:// directory (skips hidden dirs).
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


## Write text to a file (creating parent dirs) and tell the editor to re-import it.
## Used as the UndoRedo do/undo callback for script writes.
func _write_file_text(path: String, text: String) -> void:
	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(text)
		file.close()
	EditorInterface.get_resource_filesystem().update_file(path)


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
		EditorInterface.get_resource_filesystem().update_file(path)


# --- node parity handlers (issue #31) --------------------------------------

func _cmd_duplicate_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var parent := node.get_parent()
	if node == root or parent == null:
		return _fail("VALIDATION_ERROR", "Cannot duplicate the scene root.")

	var dup := node.duplicate()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Duplicate %s" % node.name)
	# force_readable_name=true so a name collision becomes "Box2", not "@Box@123".
	ur.add_do_method(parent, "add_child", dup, true)
	ur.add_do_method(self, "_own_recursive", dup, root)
	ur.add_do_reference(dup)
	ur.add_undo_method(parent, "remove_child", dup)
	ur.commit_action()
	return _ok({
		"node_path": Inspect.relative_path(dup, root),
		"source_path": str(params.get("node_path")),
	})


func _cmd_move_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var old_parent := node.get_parent()
	if node == root or old_parent == null:
		return _fail("VALIDATION_ERROR", "Cannot move the scene root.")
	var dest := _resolve(params.get("new_parent_path", ""))
	if not dest["ok"]:
		return dest
	var new_parent: Node = dest["node"]
	if new_parent == node or node.is_ancestor_of(new_parent):
		return _fail("VALIDATION_ERROR", "Cannot move a node into itself or one of its descendants.")

	var old_index := node.get_index()
	var index := int(params.get("index", -1))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Move %s" % node.name)
	ur.add_do_method(old_parent, "remove_child", node)
	ur.add_do_method(new_parent, "add_child", node)
	ur.add_do_method(self, "_own_recursive", node, root)
	if index >= 0:
		ur.add_do_method(new_parent, "move_child", node, index)
	ur.add_do_reference(node)
	ur.add_undo_method(new_parent, "remove_child", node)
	ur.add_undo_method(old_parent, "add_child", node)
	ur.add_undo_method(self, "_own_recursive", node, root)
	ur.add_undo_method(old_parent, "move_child", node, old_index)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(node, root), "moved": true})


func _cmd_add_to_group(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if node.is_in_group(group):
		return _ok({"node_path": str(params.get("node_path")), "group": group, "added": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s to group %s" % [node.name, group])
	# persistent=true so the membership is saved into the scene.
	ur.add_do_method(node, "add_to_group", group, true)
	ur.add_undo_method(node, "remove_from_group", group)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "group": group, "added": true})


func _cmd_remove_from_group(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if not node.is_in_group(group):
		return _ok({"node_path": str(params.get("node_path")), "group": group, "removed": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove %s from group %s" % [node.name, group])
	ur.add_do_method(node, "remove_from_group", group)
	ur.add_undo_method(node, "add_to_group", group, true)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "group": group, "removed": true})


func _cmd_list_signal_connections(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var connections: Array = []
	for sig in node.get_signal_list():
		var signal_name: String = sig["name"]
		for conn in node.get_signal_connection_list(signal_name):
			var callable: Callable = conn["callable"]
			var target: Object = callable.get_object()
			var target_path: String
			if target is Node and root != null:
				target_path = Inspect.relative_path(target, root)
			else:
				target_path = str(target)
			connections.append({
				"signal": signal_name,
				"target_path": target_path,
				"method": String(callable.get_method()),
				"persistent": (int(conn.get("flags", 0)) & Object.CONNECT_PERSIST) != 0,
			})
	return _ok({"node_path": str(params.get("node_path")), "connections": connections})


func _cmd_disconnect_signal(params: Dictionary) -> Dictionary:
	var src := _resolve(params.get("source_path", ""))
	if not src["ok"]:
		return src
	var tgt := _resolve(params.get("target_path", ""))
	if not tgt["ok"]:
		return tgt
	var source: Node = src["node"]
	var target: Node = tgt["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _fail("VALIDATION_ERROR", "Source has no signal '%s'." % signal_name)
	if not target.has_method(method_name):
		return _fail("VALIDATION_ERROR", "Target has no method '%s'." % method_name)
	var callable := Callable(target, method_name)
	if not source.is_connected(signal_name, callable):
		return _fail("VALIDATION_ERROR", "Signal '%s' is not connected to that method." % signal_name)

	# Capture the original flags so undo restores the connection faithfully.
	var flags := 0
	for conn in source.get_signal_connection_list(signal_name):
		if (conn["callable"] as Callable) == callable:
			flags = int(conn["flags"])
			break
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Disconnect %s" % signal_name)
	ur.add_do_method(source, "disconnect", signal_name, callable)
	ur.add_undo_method(source, "connect", signal_name, callable, flags)
	ur.commit_action()
	return _ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"disconnected": true,
	})


# --- editor screenshots (issue #33) ----------------------------------------

func _cmd_capture_editor_screenshot(_params: Dictionary) -> Dictionary:
	# Split the chain so any null intermediate returns a structured error, never crashes.
	var base_control := EditorInterface.get_base_control()
	if base_control == null:
		return _fail("INTERNAL_ERROR", "Editor base control is unavailable.")
	var viewport := base_control.get_viewport()
	if viewport == null:
		return _fail("INTERNAL_ERROR", "Editor viewport is unavailable.")
	var texture := viewport.get_texture()
	if texture == null:
		return _fail("INTERNAL_ERROR", "No viewport texture (no rendered frame; is a display available?).")
	var image := texture.get_image()
	if image == null:
		return _fail("INTERNAL_ERROR", "Could not capture the editor viewport image.")
	var result := _encode_png(image)
	if str(result.get("base64", "")).is_empty():
		return _fail("INTERNAL_ERROR", "PNG encoding produced no data.")
	return _ok(result)


## Encode an Image as a base64 PNG result (no temp files). Pure given an Image, so
## it is headless-testable with a synthetic image (see godot/tests/screenshot_smoke.gd).
func _encode_png(image: Image) -> Dictionary:
	return {
		"format": "png",
		"width": image.get_width(),
		"height": image.get_height(),
		"base64": Marshalls.raw_to_base64(image.save_png_to_buffer()),
	}


# --- project & filesystem (issue #32) --------------------------------------

func _cmd_get_filesystem_tree(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var max_depth := int(params.get("max_depth", -1))
	return _ok({"tree": _fs_node(directory, max_depth)})


func _cmd_search_files(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var name_glob := str(params.get("name_glob", ""))
	var content := str(params.get("content", ""))
	var max_results := int(params.get("max_results", 200))
	var matches: Array = []
	var truncated := _search(directory, name_glob, content, max_results, matches)
	return _ok({"matches": matches, "truncated": truncated})


func _cmd_get_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if not ProjectSettings.has_setting(setting):
		return _ok({"name": setting, "value": null, "exists": false})
	return _ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"exists": true,
	})


func _cmd_set_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if setting.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var raw: Variant = params.get("value")
	var value: Variant = raw
	if ProjectSettings.has_setting(setting):
		# Coerce to the setting's existing type so e.g. a vector dict becomes a Vector2.
		value = Coerce.from_json(raw, typeof(ProjectSettings.get_setting(setting)))
	ProjectSettings.set_setting(setting, value)
	ProjectSettings.save()
	return _ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"set": true,
	})


func _cmd_path_to_uid(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var id := ResourceLoader.get_resource_uid(path)
	if id == -1:
		return _fail("RESOURCE_NOT_FOUND", "No UID for '%s'." % path)
	return _ok({"path": path, "uid": ResourceUID.id_to_text(id)})


func _cmd_uid_to_path(params: Dictionary) -> Dictionary:
	var uid := str(params.get("uid", ""))
	var id := ResourceUID.text_to_id(uid)
	if id == -1 or not ResourceUID.has_id(id):
		return _fail("RESOURCE_NOT_FOUND", "Unknown UID '%s'." % uid)
	return _ok({"uid": uid, "path": ResourceUID.get_id_path(id)})


## Recursive filesystem node { name, path, type, children }. Skips hidden entries.
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


# --- resource files + autoloads (issue #34) --------------------------------

func _cmd_read_resource(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	return _ok({
		"resource_path": path,
		"type": res.get_class(),
		"script": Inspect.script_path(res),
		"properties": Inspect.resource_properties(res),
	})


func _cmd_create_resource(params: Dictionary) -> Dictionary:
	var res_type := str(params.get("type", ""))
	var path := str(params.get("resource_path", ""))
	if not ClassDB.class_exists(res_type) or not ClassDB.can_instantiate(res_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable type '%s'." % res_type)
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must end with .tres or .res.")
	var instance: Object = ClassDB.instantiate(res_type)
	if not (instance is Resource):
		# Free any discarded non-RefCounted instance (Node or bare Object) to avoid
		# leaking; RefCounted instances free themselves when the ref drops.
		if not (instance is RefCounted):
			instance.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a Resource type." % res_type)

	var res: Resource = instance
	var properties: Dictionary = params.get("properties", {})
	for key in properties:
		var prop_type := _property_type(res, str(key))
		if prop_type != -1:
			res.set(str(key), Coerce.from_json(properties[key], prop_type))

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var err := ResourceSaver.save(res, path)
	if err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save resource to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)
	return _ok({"resource_path": path, "type": res_type, "created": true})


func _cmd_set_resource_property(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	var property := str(params.get("property", ""))
	var prop_type := _property_type(res, property)
	if prop_type == -1:
		return _fail("VALIDATION_ERROR", "Resource has no property '%s'." % property)

	var old_value: Variant = res.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [path.get_file(), property])
	ur.add_do_method(self, "_set_and_save_resource", path, property, new_value)
	ur.add_undo_method(self, "_set_and_save_resource", path, property, old_value)
	ur.commit_action()
	return _ok({
		"resource_path": path,
		"property": property,
		"value": Coerce.to_json(ResourceLoader.load(path).get(property)),
	})


func _cmd_register_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var path := str(params.get("path", ""))
	if autoload_name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script/scene at '%s'." % path)
	# "*" prefix enables the autoload as a global singleton.
	ProjectSettings.set_setting("autoload/" + autoload_name, "*" + path)
	ProjectSettings.save()
	return _ok({"name": autoload_name, "path": path, "registered": true})


func _cmd_unregister_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var key := "autoload/" + autoload_name
	if not ProjectSettings.has_setting(key):
		return _ok({"name": autoload_name, "unregistered": false})
	ProjectSettings.set_setting(key, null)
	ProjectSettings.save()
	return _ok({"name": autoload_name, "unregistered": true})


## Load a resource, set a property, and re-save — the UndoRedo callback for edits.
func _set_and_save_resource(path: String, property: String, value: Variant) -> void:
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return
	res.set(property, value)
	ResourceSaver.save(res, path)
	EditorInterface.get_resource_filesystem().update_file(path)


## Set owner of a node and its whole subtree to the scene root so it is saved.
func _own_recursive(node: Node, root: Node) -> void:
	if node != root:
		node.owner = root
	for child in node.get_children():
		_own_recursive(child, root)


# --- editor-state helpers --------------------------------------------------

## Resolve a node by scene-relative path, returning {ok, node} or an error body.
func _resolve(raw_path: Variant) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node: Node = root.get_node_or_null(NodePath(str(raw_path)))
	if node == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(raw_path))
	return {"ok": true, "node": node}


## The Variant.Type of an object's property, or -1 if it has no such property.
func _property_type(obj: Object, property: String) -> int:
	for entry in obj.get_property_list():
		if entry["name"] == property:
			return int(entry["type"])
	return -1


func _scene_name(root: Node) -> String:
	if not root.scene_file_path.is_empty():
		return root.scene_file_path.get_file()
	return String(root.name)


func _autoloads() -> Dictionary:
	var autoloads: Dictionary = {}
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("autoload/"):
			autoloads[key.trim_prefix("autoload/")] = str(ProjectSettings.get_setting(key, ""))
	return autoloads


func _input_actions() -> Array:
	var actions: Array = []
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("input/"):
			actions.append(key.trim_prefix("input/"))
	return actions


# --- response builders -----------------------------------------------------

func _ok(result: Dictionary) -> Dictionary:
	return {"ok": true, "result": result}


func _fail(code: String, hint: String, required: String = "") -> Dictionary:
	var body: Dictionary = {"ok": false, "error": code, "hint": hint}
	if not required.is_empty():
		body["required"] = required
	return body
