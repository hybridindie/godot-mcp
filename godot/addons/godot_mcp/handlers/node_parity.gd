@tool
class_name MCPNodeParityHandlers
extends RefCounted
## Domain handler: node parity.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_to_group"] = _cmd_add_to_group
	handlers["cmd_disconnect_signal"] = _cmd_disconnect_signal
	handlers["cmd_duplicate_node"] = _cmd_duplicate_node
	handlers["cmd_list_signal_connections"] = _cmd_list_signal_connections
	handlers["cmd_move_node"] = _cmd_move_node
	handlers["cmd_remove_from_group"] = _cmd_remove_from_group


# -- handlers ----------------------------------------------------------------

func _cmd_duplicate_node(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var parent := node.get_parent()
	if node == root or parent == null:
		return _router._fail("VALIDATION_ERROR", "Cannot duplicate the scene root.")

	var dup := node.duplicate()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Duplicate %s" % node.name)
	# force_readable_name=true so a name collision becomes "Box2", not "@Box@123".
	ur.add_do_method(parent, "add_child", dup, true)
	ur.add_do_method(_router, "_own_recursive", dup, root)
	ur.add_do_reference(dup)
	ur.add_undo_method(parent, "remove_child", dup)
	ur.commit_action()
	return _router._ok({
		"node_path": Inspect.relative_path(dup, root),
		"source_path": str(params.get("node_path")),
	})



func _cmd_move_node(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var old_parent := node.get_parent()
	if node == root or old_parent == null:
		return _router._fail("VALIDATION_ERROR", "Cannot move the scene root.")
	var dest := _router._resolve(params.get("new_parent_path", ""))
	if not dest["ok"]:
		return dest
	var new_parent: Node = dest["node"]
	if new_parent == node or node.is_ancestor_of(new_parent):
		return _router._fail("VALIDATION_ERROR", "Cannot move a node into itself or one of its descendants.")

	var old_index := node.get_index()
	var index := int(params.get("index", -1))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Move %s" % node.name)
	ur.add_do_method(old_parent, "remove_child", node)
	ur.add_do_method(new_parent, "add_child", node)
	ur.add_do_method(_router, "_own_recursive", node, root)
	if index >= 0:
		ur.add_do_method(new_parent, "move_child", node, index)
	ur.add_do_reference(node)
	ur.add_undo_method(new_parent, "remove_child", node)
	ur.add_undo_method(old_parent, "add_child", node)
	ur.add_undo_method(_router, "_own_recursive", node, root)
	ur.add_undo_method(old_parent, "move_child", node, old_index)
	ur.commit_action()
	return _router._ok({"node_path": Inspect.relative_path(node, root), "moved": true})



func _cmd_add_to_group(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _router._fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if node.is_in_group(group):
		return _router._ok({"node_path": str(params.get("node_path")), "group": group, "added": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s to group %s" % [node.name, group])
	# persistent=true so the membership is saved into the scene.
	ur.add_do_method(node, "add_to_group", group, true)
	ur.add_undo_method(node, "remove_from_group", group)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "group": group, "added": true})



func _cmd_remove_from_group(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _router._fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if not node.is_in_group(group):
		return _router._ok({"node_path": str(params.get("node_path")), "group": group, "removed": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove %s from group %s" % [node.name, group])
	ur.add_do_method(node, "remove_from_group", group)
	ur.add_undo_method(node, "add_to_group", group, true)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "group": group, "removed": true})



func _cmd_list_signal_connections(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
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
	return _router._ok({"node_path": str(params.get("node_path")), "connections": connections})



func _cmd_disconnect_signal(params: Dictionary) -> Dictionary:
	var src := _router._resolve(params.get("source_path", ""))
	if not src["ok"]:
		return src
	var tgt := _router._resolve(params.get("target_path", ""))
	if not tgt["ok"]:
		return tgt
	var source: Node = src["node"]
	var target: Node = tgt["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _router._fail("VALIDATION_ERROR", "Source has no signal '%s'." % signal_name)
	if not target.has_method(method_name):
		return _router._fail("VALIDATION_ERROR", "Target has no method '%s'." % method_name)
	var callable := Callable(target, method_name)
	if not source.is_connected(signal_name, callable):
		return _router._fail("VALIDATION_ERROR", "Signal '%s' is not connected to that method." % signal_name)

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
	return _router._ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"disconnected": true,
	})


