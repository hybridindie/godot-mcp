@tool
class_name MCPSceneInspectHandlers
extends RefCounted
## Domain handler: read-only scene / node inspection (issue #5).
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_active_scene"] = _cmd_get_active_scene
	handlers["cmd_list_scenes"] = _cmd_list_scenes
	handlers["cmd_get_scene_tree"] = _cmd_get_scene_tree
	handlers["cmd_get_selected_node"] = _cmd_get_selected_node
	handlers["cmd_get_node_properties"] = _cmd_get_node_properties
	handlers["cmd_get_node_property"] = _cmd_get_node_property
	handlers["cmd_get_node_property_list"] = _cmd_get_node_property_list
	handlers["cmd_get_node_groups"] = _cmd_get_node_groups


# -- handlers ----------------------------------------------------------------

func _cmd_get_active_scene(_params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._ok({"is_open": false, "path": null, "name": null})
	return _router._ok({"is_open": true, "path": root.scene_file_path, "name": _router._scene_name(root)})


## List every res://*.tscn in the project + which is main / open / active (#304), so an
## agent can decide open-vs-create when no scene is open. Read-only; JSON-safe.
func _cmd_list_scenes(_params: Dictionary) -> Dictionary:
	var main_scene: String = str(ProjectSettings.get_setting("application/run/main_scene", ""))
	var open_set: Dictionary = {}
	for p in EditorInterface.get_open_scenes():
		open_set[p] = true
	var active_root: Node = EditorInterface.get_edited_scene_root()
	var active_path: String = active_root.scene_file_path if active_root != null else ""

	var paths: Array = []
	_collect_scene_files("res://", paths)
	paths.sort()

	var scenes: Array = []
	for path in paths:
		scenes.append({
			"path": path,
			"is_main": path == main_scene,
			"is_open": open_set.has(path),
			"is_active": active_path != "" and path == active_path,
		})
	return _router._ok({
		"scenes": scenes,
		"main_scene": (main_scene if main_scene != "" else null),
	})


## Recursively collect res://*.tscn / *.scn paths (skips hidden dirs like .godot),
## mirroring the DirAccess walk in project_fs.gd.
func _collect_scene_files(dir_path: String, out: Array) -> void:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				_collect_scene_files(full, out)
			elif name.ends_with(".tscn") or name.ends_with(".scn"):
				out.append(full)
		name = dir.get_next()
	dir.list_dir_end()


func _cmd_get_scene_tree(params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._ok({"tree": null})
	var max_depth := int(params.get("max_depth", -1))
	var lightweight := bool(params.get("lightweight", false))
	return _router._ok({"tree": Inspect.serialize_tree(root, max_depth, lightweight)})


func _cmd_get_selected_node(_params: Dictionary) -> Dictionary:
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.is_empty():
		return _router._ok({"selected": null})
	var root: Node = EditorInterface.get_edited_scene_root()
	return _router._ok({"selected": Inspect.node_info(selected[0], root if root != null else selected[0])})


func _cmd_get_node_properties(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := Inspect.normalize_node_path(str(params["node_path"]))
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	return _router._ok(Inspect.node_info(node, root))


func _cmd_get_node_property(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	if not params.has("property"):
		return _router._fail("VALIDATION_ERROR", "'property' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := Inspect.normalize_node_path(str(params["node_path"]))
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	var read: Dictionary = Inspect.read_property(node, str(params["property"]))
	return _router._ok({
		"node_path": str(params["node_path"]),
		"property": str(params["property"]),
		"value": read["value"],
		"exists": read["exists"],
	})


func _cmd_get_node_groups(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := Inspect.normalize_node_path(str(params["node_path"]))
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	return _router._ok({"node_path": str(params["node_path"]), "groups": Inspect.node_groups(node)})


func _cmd_get_node_property_list(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := Inspect.normalize_node_path(str(params["node_path"]))
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	var names: Array = []
	for entry in node.get_property_list():
		names.append(str(entry["name"]))
	return _router._ok({
		"node_path": str(params["node_path"]),
		"type": node.get_class(),
		"properties": names,
	})
