@tool
class_name MCPMutationHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: mutation.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_attach_script"] = _cmd_attach_script
	handlers["cmd_connect_signal"] = _cmd_connect_signal
	handlers["cmd_create_node"] = _cmd_create_node
	handlers["cmd_create_scene"] = _cmd_create_scene
	handlers["cmd_delete_node"] = _cmd_delete_node
	handlers["cmd_rename_node"] = _cmd_rename_node
	handlers["cmd_save_scene"] = _cmd_save_scene
	handlers["cmd_set_node_property"] = _cmd_set_node_property


# -- handlers ----------------------------------------------------------------

func _cmd_create_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_type := str(params.get("node_type", ""))
	if not ClassDB.class_exists(node_type) or not ClassDB.can_instantiate(node_type):
		return _router._fail("VALIDATION_ERROR", "Unknown or non-instantiable node type '%s'." % node_type)
	var parent_path := str(params.get("parent_path", "."))
	if parent_path.begins_with("/"):
		parent_path = parent_path.substr(1)
	if parent_path.is_empty():
		parent_path = "."
	var parent: Node = root.get_node_or_null(NodePath(parent_path))
	if parent == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params.get("parent_path")))

	var node: Node = ClassDB.instantiate(node_type)
	node.name = str(params.get("name", node_type))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create %s" % node.name)
	ur.add_do_method(parent, "add_child", node)
	ur.add_do_method(node, "set_owner", root)
	ur.add_do_reference(node)
	ur.add_undo_method(parent, "remove_child", node)
	ur.commit_action()
	return _router._ok({"node_path": Inspect.relative_path(node, root), "created": true})



func _cmd_rename_node(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var old_name := String(node.name)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Rename %s" % old_name)
	ur.add_do_property(node, "name", str(params.get("new_name", old_name)))
	ur.add_undo_property(node, "name", old_name)
	ur.commit_action()
	return _router._ok({
		"node_path": Inspect.relative_path(node, EditorInterface.get_edited_scene_root()),
		"old_name": old_name,
		"new_name": String(node.name),
		"renamed": true,
	})



func _cmd_set_node_property(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var property := str(params.get("property", ""))
	var prop_type := _router._property_type(node, property)
	if prop_type == -1:
		return _router._fail("VALIDATION_ERROR", "Node has no property '%s'." % property)

	var old_value: Variant = node.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [String(node.name), property])
	ur.add_do_property(node, property, new_value)
	ur.add_undo_property(node, property, old_value)
	ur.commit_action()
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"property": property,
		"value": Coerce.to_json(node.get(property)),
		"set": true,
	})



func _cmd_delete_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if node == root:
		return _router._fail("VALIDATION_ERROR", "Cannot delete the scene root.")
	# Server enforces the safety class; the addon honors the confirm flag too.
	if not bool(params.get("confirm", false)):
		return _router._fail("PRECONDITION_FAILED", "Deleting a node requires confirm=true.", "confirm")

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
	return _router._ok({"node_path": str(params.get("node_path")), "deleted": true})



func _cmd_attach_script(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var script_path := str(params.get("script_path", ""))
	if not ResourceLoader.exists(script_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'. Create it first." % script_path)
	var script: Variant = load(script_path)
	if not (script is Script):
		return _router._fail("VALIDATION_ERROR", "'%s' is not a script resource." % script_path)

	var old_script: Variant = node.get_script()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Attach script to %s" % node.name)
	ur.add_do_method(node, "set_script", script)
	ur.add_undo_method(node, "set_script", old_script)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "script_path": script_path, "attached": true})



func _cmd_connect_signal(params: Dictionary) -> Dictionary:
	var source_found := _router._resolve(params.get("source_path", ""))
	if not source_found["ok"]:
		return source_found
	var target_found := _router._resolve(params.get("target_path", ""))
	if not target_found["ok"]:
		return target_found
	var source: Node = source_found["node"]
	var target: Node = target_found["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _router._fail(
			"VALIDATION_ERROR",
			"Source '%s' has no signal '%s'. Available: %s." % [source.name, signal_name, _signal_names_hint(source)]
		)
	var callable := Callable(target, method_name)
	# Check the idempotent path FIRST: a connection already present (often
	# persisted in the scene file) is success, not failure — and short-circuiting
	# here means a method-resolution quirk can never turn an existing connection
	# into a false failure (the original bug class in #152).
	if source.is_connected(signal_name, callable):
		return _router._ok({
			"source_path": str(params.get("source_path")),
			"signal_name": signal_name,
			"target_path": str(params.get("target_path")),
			"method_name": method_name,
			"connected": true,
			"already_connected": true,
		})
	# For a *fresh* connect, the method must resolve. has_method() already covers
	# script methods and built-in virtuals (e.g. _ready); the script method-list
	# is a fallback for tool-script methods not yet registered on the instance.
	if not _has_callable_method(target, method_name):
		return _router._fail(
			"VALIDATION_ERROR",
			"Target '%s' has no method '%s'. Attach a script defining it, or choose an existing method." % [target.name, method_name]
		)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Connect %s" % signal_name)
	# CONNECT_PERSIST so the connection is saved into the scene file.
	ur.add_do_method(source, "connect", signal_name, callable, Object.CONNECT_PERSIST)
	ur.add_undo_method(source, "disconnect", signal_name, callable)
	ur.commit_action()
	return _router._ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"connected": true,
		"already_connected": false,
	})


func _has_callable_method(node: Node, method_name: String) -> bool:
	if node.has_method(method_name):
		return true
	var script: Script = node.get_script()
	if script != null:
		for m in script.get_script_method_list():
			if str(m.get("name", "")) == method_name:
				return true
	return false


func _signal_names_hint(node: Node) -> String:
	var names := PackedStringArray()
	for s in node.get_signal_list():
		names.append(str(s.get("name", "")))
		if names.size() >= 8:
			break
	return ", ".join(names)



func _cmd_save_scene(_params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	if root.scene_file_path.is_empty():
		return _router._fail("PRECONDITION_FAILED", "Scene has no path yet; create it with a path first.", "scene_path")
	var err := EditorInterface.save_scene()
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save scene (error %d)." % err)
	return _router._ok({"path": root.scene_file_path, "saved": true})



func _cmd_create_scene(params: Dictionary) -> Dictionary:
	var root_type := str(params.get("root_type", ""))
	var scene_path := str(params.get("scene_path", ""))
	if not ClassDB.class_exists(root_type) or not ClassDB.can_instantiate(root_type):
		return _router._fail("VALIDATION_ERROR", "Unknown or non-instantiable root type '%s'." % root_type)
	if not scene_path.ends_with(".tscn") and not scene_path.ends_with(".scn"):
		return _router._fail("VALIDATION_ERROR", "scene_path must end with .tscn or .scn.")

	var root: Node = ClassDB.instantiate(root_type)
	root.name = scene_path.get_file().get_basename()
	var packed := PackedScene.new()
	var pack_err := packed.pack(root)
	root.free()
	if pack_err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to pack scene (error %d)." % pack_err)
	# Auto-create the parent directory (parity with _write_file_text) — a missing
	# dir surfaced as an opaque ResourceSaver "error 19" (#412).
	var base_dir := scene_path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		var mkdir_err := DirAccess.make_dir_recursive_absolute(
			ProjectSettings.globalize_path(base_dir)
		)
		if mkdir_err != OK:
			return _router._fail(
				"PRECONDITION_FAILED",
				"Could not create parent directory '%s' for the new scene (error %d)."
					% [base_dir, mkdir_err],
				"parent_dir",
			)
	var save_err := ResourceSaver.save(packed, scene_path)
	if save_err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save scene to '%s' (error %d)." % [scene_path, save_err])
	# Creating a file isn't an UndoRedo-tracked tree edit; open it for editing.
	EditorInterface.open_scene_from_path(scene_path)
	return _router._ok({"scene_path": scene_path, "root_type": root_type, "created": true})


