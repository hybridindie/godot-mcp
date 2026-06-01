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


# --- editor-state helpers --------------------------------------------------

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
