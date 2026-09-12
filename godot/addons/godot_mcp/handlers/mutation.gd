@tool
class_name MCPMutationHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
## Domain handler: mutation.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("../scene_inspect.gd")

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



## Whether the node is an entry the edited scene's *base* scene defines (not
## the root). GDScript has no `Node.get_scene_inherited_state()`, so read the
## base state off the edited scene's PackedScene and match node paths (4.7).
func _inherited_from_base(node: Node, root: Node) -> bool:
	var scene_path := root.scene_file_path
	if scene_path.is_empty():
		return false
	var scene: PackedScene = ResourceLoader.load(scene_path)
	if scene == null:
		return false
	var base_state: SceneState = scene.get_state().get_base_scene_state()
	if base_state == null:
		return false
	var path := str(root.get_path_to(node))
	for i in range(base_state.get_node_count()):
		var base_path := str(base_state.get_node_path(i, false))
		# `path(false)` is scene-relative ("./Cold"); the root entry is "" and
		# must stay renamable, so only nested paths can refuse.
		if base_path == "./" + path and not base_state.is_node_instance_placeholder(i):
			return true
	return false


func _cmd_rename_node(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	# #473: refuse the renames the editor itself refuses
	# (SceneTreeDock::_validate_no_foreign_selected, 4.7) — allowing them
	# corrupts the save (an inherited-scene rename duplicates the node; an
	# instanced-child rename is silently dropped). The refusal must precede
	# any UndoRedo action so the rejected rename never becomes an undo step.
	if node != root and node.owner != root:
		var source := "the edited scene's root"
		if node.owner != null and not node.owner.scene_file_path.is_empty():
			source = node.owner.scene_file_path
		return _router._fail(
			"VALIDATION_ERROR",
			"Node '%s' comes from the instanced scene '%s'; the editor refuses to rename it here — the rename would be lost on save. Rename it in '%s' (or its source scene) instead." % [root.get_path_to(node), source, source],
			"node_path",
		)
	if node != root and _inherited_from_base(node, root):
		return _router._fail(
			"VALIDATION_ERROR",
			"Node '%s' comes from the base scene this scene inherits; renaming it here packs a duplicate node on save. Rename it in the base scene instead." % root.get_path_to(node),
			"node_path",
		)
	var old_name := String(node.name)
	# The persistence verdict is stamped BEFORE the rename (#481): the probe a
	# preview sent named this node by its pre-rename path, so the real run's
	# verdict must describe the same target (the hint says 'Relic/Cold/Extra',
	# not 'Relic/Cold/Extra2') — the node is the same object either way.
	var persistence := _router._persistent_target(node)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Rename %s" % old_name)
	ur.add_do_property(node, "name", str(params.get("new_name", old_name)))
	ur.add_undo_property(node, "name", old_name)
	ur.commit_action()
	return _router._ok(_router._with_persistence({
		"node_path": Inspect.relative_path(node, EditorInterface.get_edited_scene_root()),
		"old_name": old_name,
		"new_name": String(node.name),
		"renamed": true,
	}, persistence))



func _cmd_set_node_property(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var property := str(params.get("property", ""))
	var prop_type := _router._property_type(node, property)
	if prop_type == -1:
		return _router._fail("VALIDATION_ERROR", "Node has no property '%s'." % property)

	# Object-typed properties accept a res:// path and load it (issue #414) —
	# the generic from_json falls through to the raw value, which set() then
	# silently no-ops on a typed Object property while reporting success.
	var new_value: Variant
	if prop_type == TYPE_OBJECT:
		var coerced: Dictionary = Coerce.object_from_json(params.get("value"))
		if not bool(coerced.get("ok", false)):
			return _router._fail(
				str(coerced.get("error", "VALIDATION_ERROR")),
				"Setting '%s' failed: %s" % [property, str(coerced.get("hint", ""))],
				"value",
			)
		new_value = coerced["value"]
	else:
		new_value = Coerce.from_json(params.get("value"), prop_type)

	var old_value: Variant = node.get(property)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [String(node.name), property])
	ur.add_do_property(node, property, new_value)
	ur.add_undo_property(node, property, old_value)
	ur.commit_action()
	var read_back: Variant = node.get(property)
	# The echo is the agent's only verifier: a null read-back after a non-null
	# write means the engine rejected the assignment (e.g. a dimension/type
	# mismatch) — report that, never set:true (issue #414).
	if read_back == null and new_value != null:
		return _router._fail(
			"VALIDATION_ERROR",
			"Setting '%s' did not land (reads back null after the set). The value may be "
				+ "incompatible with the property's expected type." % property,
			"value",
		)
	return _router._ok(_router._with_persistence({
		"node_path": str(params.get("node_path")),
		"property": property,
		"value": Coerce.to_json(read_back),
		"set": true,
	}, _router._persistent_target(node)))



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
	return _router._ok(_router._with_persistence({"node_path": str(params.get("node_path")), "script_path": script_path, "attached": true}, _router._persistent_target(node)))



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


