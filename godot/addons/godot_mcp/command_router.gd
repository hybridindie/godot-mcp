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
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Delete %s" % node.name)
	ur.add_do_method(parent, "remove_child", node)
	ur.add_undo_method(parent, "add_child", node)
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


## The Variant.Type of a node property, or -1 if the node has no such property.
func _property_type(node: Node, property: String) -> int:
	for entry in node.get_property_list():
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
