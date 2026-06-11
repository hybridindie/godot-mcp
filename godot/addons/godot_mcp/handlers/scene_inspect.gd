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
	handlers["cmd_get_scene_tree"] = _cmd_get_scene_tree
	handlers["cmd_get_selected_node"] = _cmd_get_selected_node
	handlers["cmd_get_node_properties"] = _cmd_get_node_properties
	handlers["cmd_get_node_property_list"] = _cmd_get_node_property_list


# -- handlers ----------------------------------------------------------------

func _cmd_get_active_scene(_params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._ok({"is_open": false, "path": null, "name": null})
	return _router._ok({"is_open": true, "path": root.scene_file_path, "name": _router._scene_name(root)})


func _cmd_get_scene_tree(params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._ok({"tree": null})
	var max_depth := int(params.get("max_depth", -1))
	return _router._ok({"tree": Inspect.serialize_tree(root, max_depth)})


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
	var node_path := str(params["node_path"])
	if node_path.begins_with("/"):
		node_path = node_path.substr(1)
	# Also strip "root/" prefix commonly hallucinated by LLMs
	if node_path.begins_with("root/"):
		node_path = node_path.substr(5)
	if node_path.is_empty():
		node_path = "."
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	return _router._ok(Inspect.node_info(node, root))


func _cmd_get_node_property_list(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := str(params["node_path"])
	if node_path.begins_with("/"):
		node_path = node_path.substr(1)
	# Also strip "root/" prefix commonly hallucinated by LLMs
	if node_path.begins_with("root/"):
		node_path = node_path.substr(5)
	if node_path.is_empty():
		node_path = "."
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
