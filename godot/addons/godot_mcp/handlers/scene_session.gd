@tool
class_name MCPSceneSessionHandlers
extends RefCounted
## Domain handler: scene session.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_instance_scene"] = _cmd_instance_scene
	handlers["cmd_list_open_scenes"] = _cmd_list_open_scenes
	handlers["cmd_open_scene"] = _cmd_open_scene
	handlers["cmd_reload_scene"] = _cmd_reload_scene
	handlers["cmd_save_all_scenes"] = _cmd_save_all_scenes
	handlers["cmd_select_nodes"] = _cmd_select_nodes


# -- handlers ----------------------------------------------------------------

func _cmd_open_scene(params: Dictionary) -> Dictionary:
	var scene_path := str(params.get("scene_path", ""))
	if scene_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "scene_path is required.")
	if not FileAccess.file_exists(scene_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No scene at '%s'." % scene_path)
	var open_paths: PackedStringArray = EditorInterface.get_open_scenes()
	var already_open := false
	for p in open_paths:
		if str(p) == scene_path:
			already_open = true
			break
	EditorInterface.open_scene_from_path(scene_path)
	return _router._ok({"scene_path": scene_path, "opened": true, "already_open": already_open})



func _cmd_reload_scene(params: Dictionary) -> Dictionary:
	var scene_path := str(params.get("scene_path", ""))
	if scene_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "scene_path is required.")
	# confirm is a server-side safety gate; we honor it defensively addon-side too.
	if not params.get("confirm", false):
		return _router._fail("PRECONDITION_FAILED", "This call discards unsaved changes. Set confirm=True to proceed.", "confirm")
	var open_paths: PackedStringArray = EditorInterface.get_open_scenes()
	var is_open := false
	for p in open_paths:
		if str(p) == scene_path:
			is_open = true
			break
	if not is_open:
		return _router._fail("PRECONDITION_FAILED", "Scene '%s' is not open. Open it first." % scene_path, "open_scene")
	EditorInterface.reload_scene_from_path(scene_path)
	return _router._ok({"scene_path": scene_path, "reloaded": true})



func _cmd_save_all_scenes(_params: Dictionary) -> Dictionary:
	EditorInterface.save_all_scenes()
	var count := EditorInterface.get_open_scenes().size()
	return _router._ok({"saved": true, "count": count})



func _cmd_list_open_scenes(_params: Dictionary) -> Dictionary:
	var paths: PackedStringArray = EditorInterface.get_open_scenes()
	var scenes: Array = []
	for p in paths:
		scenes.append({"path": str(p)})
	return _router._ok({"scenes": scenes})



func _cmd_select_nodes(params: Dictionary) -> Dictionary:
	var raw_paths: Variant = params.get("node_paths", [])
	if raw_paths is String:
		return _router._fail("VALIDATION_ERROR", "node_paths must be an array of scene-relative paths.")
	var node_paths: Array = raw_paths as Array
	if node_paths.is_empty():
		return _router._fail("VALIDATION_ERROR", "Provide at least one node path in node_paths.")
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var selection := EditorInterface.get_selection()
	selection.clear()
	var selected: Array = []
	for raw_path in node_paths:
		var path_str := str(raw_path)
		if path_str.begins_with("/"):
			path_str = path_str.substr(1)
		if path_str.is_empty():
			path_str = "."
		var node := root.get_node_or_null(NodePath(path_str))
		if node == null:
			return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % path_str)
		selection.add_node(node)
		selected.append(path_str)
	var scene_path := root.scene_file_path if not root.scene_file_path.is_empty() else ""
	return _router._ok({"scene_path": scene_path, "selected": selected, "count": selected.size()})



func _cmd_instance_scene(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var parent_path := str(params.get("parent_path", "."))
	if parent_path.begins_with("/"):
		parent_path = parent_path.substr(1)
	if parent_path.is_empty():
		parent_path = "."
	var parent: Node = root.get_node_or_null(NodePath(parent_path))
	if parent == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % parent_path)

	var scene_path := str(params.get("scene_path", ""))
	if not FileAccess.file_exists(scene_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No scene at '%s'." % scene_path)
	var packed: PackedScene = load(scene_path)
	if packed == null:
		return _router._fail("VALIDATION_ERROR", "Failed to load PackedScene from '%s'." % scene_path)

	var instance: Node = packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	var custom_name := str(params.get("name", ""))
	if not custom_name.is_empty():
		instance.name = custom_name
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Instance %s" % scene_path.get_file())
	ur.add_do_method(parent, "add_child", instance)
	ur.add_do_method(instance, "set_owner", root)
	ur.add_do_reference(instance)
	ur.add_undo_method(parent, "remove_child", instance)
	ur.commit_action()
	return _router._ok({"node_path": Inspect.relative_path(instance, root), "scene_path": scene_path, "instanced": true})


