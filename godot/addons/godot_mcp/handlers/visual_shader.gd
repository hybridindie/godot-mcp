@tool
class_name MCPVisualShaderHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
const VisualShaderRead := preload("../visual_shader_read.gd")
## Domain handler: visual shader node graphs (issue #107).
##
## Registered by the router on _init(). Each handler receives a params dict and
## returns a response body via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_create_visual_shader"] = _cmd_create_visual_shader
	handlers["cmd_add_shader_node"] = _cmd_add_shader_node
	handlers["cmd_connect_shader_nodes"] = _cmd_connect_shader_nodes
	handlers["cmd_set_shader_node_param"] = _cmd_set_shader_node_param
	handlers["cmd_list_shader_node_types"] = _cmd_list_shader_node_types
	handlers["cmd_read_visual_shader"] = _cmd_read_visual_shader
	handlers["cmd_create_shader_group"] = _cmd_create_shader_group
	handlers["cmd_rename_shader_group"] = _cmd_rename_shader_group
	handlers["cmd_remove_shader_group"] = _cmd_remove_shader_group
	handlers["cmd_add_shader_group_node"] = _cmd_add_shader_group_node
	handlers["cmd_remove_shader_group_node"] = _cmd_remove_shader_group_node


# -- helpers -----------------------------------------------------------------

func _mode_from_string(mode_str: String) -> int:
	match mode_str.to_lower():
		"canvas_item", "2d":
			return VisualShader.MODE_CANVAS_ITEM
		"particles":
			return VisualShader.MODE_PARTICLES
		"sky":
			return VisualShader.MODE_SKY
		"fog":
			return VisualShader.MODE_FOG
		_:  # spatial, 3d, or unknown default
			return VisualShader.MODE_SPATIAL


func _save_visual_shader(shader: VisualShader, path: String) -> void:
	ResourceSaver.save(shader, path)
	EditorInterface.get_resource_filesystem().update_file(path)


# -- handlers ----------------------------------------------------------------

func _cmd_create_visual_shader(params: Dictionary) -> Dictionary:
	var name := str(params.get("name", ""))
	var type_str := str(params.get("type", "3d"))
	var path := str(params.get("path", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be non-empty.")
	if path.is_empty():
		path = "res://shaders/%s.tres" % name
	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "path must start with res://.")

	var shader := VisualShader.new()
	shader.set_mode(_mode_from_string(type_str))

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(base_dir)):
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(base_dir))

	var err := ResourceSaver.save(shader, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save visual shader (error %d)." % err)
	EditorInterface.get_resource_filesystem().update_file(path)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create visual shader", UndoRedo.MERGE_DISABLE, _router.asset_action_context())
	# #683: register BOTH sides so redo recreates the file after an undo removed it
	# (a fresh create with only an undo can't be redone). Capture the saved bytes.
	ur.add_do_method(_router, "_write_file_bytes", path, FileAccess.get_file_as_bytes(path))
	ur.add_undo_method(_router, "_remove_file_with_uid", path)
	ur.commit_action()

	return _router._ok({"path": path, "created": true})


func _cmd_add_shader_node(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	var node_type := str(params.get("node_type", ""))
	var node_id := int(params.get("node_id", -1))
	var position := Coerce.from_json(params.get("position", [0.0, 0.0]), TYPE_VECTOR2)

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	# Godot reserves node ids 0 (output) and 1; add_node requires id >= 2.
	if node_id < 2:
		return _router._fail("VALIDATION_ERROR", "'node_id' must be >= 2 (0 and 1 are reserved).")
	if not ClassDB.class_exists(node_type):
		return _router._fail("VALIDATION_ERROR", "Unknown node type '%s'." % node_type)
	if not ClassDB.can_instantiate(node_type):
		return _router._fail("VALIDATION_ERROR", "'%s' cannot be instantiated." % node_type)

	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var instance: Object = ClassDB.instantiate(node_type)
	if not (instance is VisualShaderNode):
		if not (instance is RefCounted):
			instance.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a VisualShaderNode." % node_type)
	var node: VisualShaderNode = instance

	var mode: int = int(shader.get_mode())
	# VisualShader has no has_node(); existence is checked via the node-id list.
	if node_id in shader.get_node_list(mode):
		return _router._fail("VALIDATION_ERROR", "Node id %d already exists." % node_id)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add shader node %s" % node_type)
	ur.add_do_method(shader, "add_node", mode, node, position, node_id)
	ur.add_undo_method(shader, "remove_node", mode, node_id)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(node)
	ur.commit_action()

	return _router._ok({"node_id": node_id, "node_type": node_type, "added": true})


func _cmd_connect_shader_nodes(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	var from_node := int(params.get("from_node", -1))
	var from_port := int(params.get("from_port", -1))
	var to_node := int(params.get("to_node", -1))
	var to_port := int(params.get("to_port", -1))

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var mode: int = int(shader.get_mode())

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Connect shader nodes")
	ur.add_do_method(shader, "connect_nodes", mode, from_node, from_port, to_node, to_port)
	ur.add_undo_method(shader, "disconnect_nodes", mode, from_node, from_port, to_node, to_port)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.commit_action()

	return _router._ok({"connected": true})


func _cmd_set_shader_node_param(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	var node_id := int(params.get("node_id", -1))
	var property := str(params.get("property", ""))
	var raw_value: Variant = params.get("value")

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if property.is_empty():
		return _router._fail("VALIDATION_ERROR", "'property' must be non-empty.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var mode: int = int(shader.get_mode())
	# VisualShader has no has_node(); existence is checked via the node-id list.
	if node_id not in shader.get_node_list(mode):
		return _router._fail("VALIDATION_ERROR", "No node with id %d in shader." % node_id)
	var node: VisualShaderNode = shader.get_node(mode, node_id)

	var prop_type := _router._helpers.property_type(node, property)
	if prop_type == -1:
		return _router._fail("VALIDATION_ERROR", "Node has no property '%s'." % property)
	var value: Variant = Coerce.from_json(raw_value, prop_type)
	var old_value: Variant = node.get(property)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set shader node param %s" % property)
	ur.add_do_method(node, "set", property, value)
	ur.add_undo_method(node, "set", property, old_value)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.commit_action()

	return _router._ok({"node_id": node_id, "property": property, "value": value, "set": true})


func _cmd_list_shader_node_types(_params: Dictionary) -> Dictionary:
	var types: Array = []
	for cls in ClassDB.get_class_list():
		if str(cls).begins_with("VisualShaderNode") and ClassDB.can_instantiate(str(cls)):
			types.append(str(cls))
	return _router._ok({"types": types})


## Read a VisualShader graph — mode + nodes + connections (issue #219 G6). The inverse of
## the visual-shader writers; delegates the pure serialization to MCPVisualShaderRead.
func _cmd_read_visual_shader(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var resource: Resource = ResourceLoader.load(path)
	if not (resource is VisualShader):
		return _router._fail("VALIDATION_ERROR", "'%s' is not a VisualShader." % path)
	var data: Dictionary = VisualShaderRead.serialize(resource)
	data["shader_path"] = path
	return _router._ok(data)


# -- node groups / subgraphs (Godot 4.8, issue #601) --------------------------

## VisualShaderGroup / VisualShaderNodeGroup are 4.8+. ClassDB.class_exists()
## gate keeps this script parsing on the 4.4–4.7 floor and lets every verb fail
## honestly there instead of crashing on an unknown class.
func _groups_supported() -> bool:
	return ClassDB.class_exists("VisualShaderGroup") and ClassDB.class_exists("VisualShaderNodeGroup")


func _groups_unsupported() -> Dictionary:
	return _router._fail(
		"UNSUPPORTED",
		"VisualShader node groups require Godot 4.8+; this editor is %s." % Engine.get_version_info().get("string", ""),
		"godot_version",
	)


## Resolve a group's representative node + resource by its node id in the shader.
## Returns {ok, node, group} or {ok: false, error, hint}.
func _resolve_group(shader: VisualShader, mode: int, node_id: int) -> Dictionary:
	if not (node_id in shader.get_node_list(mode)):
		return {"ok": false, "error": "RESOURCE_NOT_FOUND", "hint": "No node with id %d in shader." % node_id}
	var node: VisualShaderNode = shader.get_node(mode, node_id)
	if node == null or not node.has_method("get_group"):
		return {"ok": false, "error": "VALIDATION_ERROR", "hint": "Node id %d is not a VisualShader group node." % node_id}
	var group: Variant = node.call("get_group")
	if not (group is Resource):
		return {"ok": false, "error": "PRECONDITION_FAILED", "hint": "Group node id %d has no VisualShaderGroup resource." % node_id}
	return {"ok": true, "node": node, "group": group}


## Connections touching `node_id` from a get_node_connections() array — captured so
## undo restores the wiring a remove_node would otherwise drop.
func _connections_touching(connections: Array, node_id: int) -> Array:
	var touching: Array = []
	for connection in connections:
		if int(connection["from_node"]) == node_id or int(connection["to_node"]) == node_id:
			touching.append(connection)
	return touching


## Undo helper for remove_shader_group: re-add the group node and re-wire it.
func _restore_shader_group_node(shader: VisualShader, mode: int, node: VisualShaderNode, position: Vector2, node_id: int, connections: Array) -> void:
	shader.add_node(mode, node, position, node_id)
	for connection in connections:
		shader.connect_nodes_forced(
			mode,
			int(connection["from_node"]),
			int(connection["from_port"]),
			int(connection["to_node"]),
			int(connection["to_port"]),
		)


## Undo helper for remove_shader_group_node: re-add the member node and re-wire it
## inside the group's graph.
func _restore_group_node(group: Resource, node: VisualShaderNode, position: Vector2, node_id: int, connections: Array) -> void:
	group.call("add_node", node, position, node_id)
	for connection in connections:
		group.call(
			"connect_nodes_forced",
			int(connection["from_node"]),
			int(connection["from_port"]),
			int(connection["to_node"]),
			int(connection["to_port"]),
		)


func _cmd_create_shader_group(params: Dictionary) -> Dictionary:
	if not _groups_supported():
		return _groups_unsupported()
	var path := str(params.get("shader_path", ""))
	var group_name := str(params.get("name", ""))
	var node_id := int(params.get("node_id", -1))
	var position := Coerce.from_json(params.get("position", [0.0, 0.0]), TYPE_VECTOR2)

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if group_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be non-empty.")
	if node_id < 2:
		return _router._fail("VALIDATION_ERROR", "'node_id' must be >= 2 (0 and 1 are reserved).")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var mode: int = int(shader.get_mode())
	if node_id in shader.get_node_list(mode):
		return _router._fail("VALIDATION_ERROR", "Node id %d already exists." % node_id)

	var group: Resource = ClassDB.instantiate("VisualShaderGroup")
	if group == null:
		return _router._fail("INTERNAL_ERROR", "Could not instantiate VisualShaderGroup.")
	group.call("set_group_name", group_name)
	var group_node: VisualShaderNode = ClassDB.instantiate("VisualShaderNodeGroup")
	if group_node == null:
		return _router._fail("INTERNAL_ERROR", "Could not instantiate VisualShaderNodeGroup.")
	group_node.call("set_group", group)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create shader group %s" % group_name)
	ur.add_do_method(shader, "add_node", mode, group_node, position, node_id)
	ur.add_undo_method(shader, "remove_node", mode, node_id)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(group_node)
	ur.commit_action()

	return _router._ok({"node_id": node_id, "name": group_name, "created": true})


func _cmd_rename_shader_group(params: Dictionary) -> Dictionary:
	if not _groups_supported():
		return _groups_unsupported()
	var path := str(params.get("shader_path", ""))
	var node_id := int(params.get("node_id", -1))
	var new_name := str(params.get("name", ""))

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if new_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be non-empty.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var resolved := _resolve_group(shader, int(shader.get_mode()), node_id)
	if not resolved["ok"]:
		return _router._fail(str(resolved["error"]), str(resolved["hint"]))
	var group: Resource = resolved["group"]
	var old_name := str(group.call("get_group_name"))

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Rename shader group")
	ur.add_do_method(group, "set_group_name", new_name)
	ur.add_undo_method(group, "set_group_name", old_name)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(group)
	ur.commit_action()

	return _router._ok({"node_id": node_id, "name": new_name, "renamed": true})


func _cmd_remove_shader_group(params: Dictionary) -> Dictionary:
	if not _groups_supported():
		return _groups_unsupported()
	var path := str(params.get("shader_path", ""))
	var node_id := int(params.get("node_id", -1))

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var mode: int = int(shader.get_mode())
	var resolved := _resolve_group(shader, mode, node_id)
	if not resolved["ok"]:
		return _router._fail(str(resolved["error"]), str(resolved["hint"]))
	var group_node: VisualShaderNode = resolved["node"]
	var group: Resource = resolved["group"]
	var group_name := str(group.call("get_group_name"))
	var position: Vector2 = shader.get_node_position(mode, node_id)
	var connections: Array = _connections_touching(shader.get_node_connections(mode), node_id)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove shader group %s" % group_name)
	ur.add_do_method(shader, "remove_node", mode, node_id)
	ur.add_undo_method(self, "_restore_shader_group_node", shader, mode, group_node, position, node_id, connections)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(group_node)
	ur.commit_action()

	return _router._ok({"node_id": node_id, "name": group_name, "removed": true})


func _cmd_add_shader_group_node(params: Dictionary) -> Dictionary:
	if not _groups_supported():
		return _groups_unsupported()
	var path := str(params.get("shader_path", ""))
	var group_node_id := int(params.get("group_node_id", -1))
	var node_type := str(params.get("node_type", ""))
	var node_id := int(params.get("node_id", -1))
	var position := Coerce.from_json(params.get("position", [0.0, 0.0]), TYPE_VECTOR2)

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	# Group graphs have no reserved output node, so id 0 is available here.
	if node_id < 0:
		return _router._fail("VALIDATION_ERROR", "'node_id' must be >= 0.")
	if not ClassDB.class_exists(node_type):
		return _router._fail("VALIDATION_ERROR", "Unknown node type '%s'." % node_type)
	if not ClassDB.can_instantiate(node_type):
		return _router._fail("VALIDATION_ERROR", "'%s' cannot be instantiated." % node_type)
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var resolved := _resolve_group(shader, int(shader.get_mode()), group_node_id)
	if not resolved["ok"]:
		return _router._fail(str(resolved["error"]), str(resolved["hint"]))
	var group: Resource = resolved["group"]
	if node_id in group.call("get_node_list"):
		return _router._fail("VALIDATION_ERROR", "Node id %d already exists in group." % node_id)

	var instance: Object = ClassDB.instantiate(node_type)
	if not (instance is VisualShaderNode):
		if not (instance is RefCounted):
			instance.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a VisualShaderNode." % node_type)
	var node: VisualShaderNode = instance

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add shader group node %s" % node_type)
	ur.add_do_method(group, "add_node", node, position, node_id)
	ur.add_undo_method(group, "remove_node", node_id)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(node)
	ur.commit_action()

	return _router._ok({"group_node_id": group_node_id, "node_id": node_id, "node_type": node_type, "added": true})


func _cmd_remove_shader_group_node(params: Dictionary) -> Dictionary:
	if not _groups_supported():
		return _groups_unsupported()
	var path := str(params.get("shader_path", ""))
	var group_node_id := int(params.get("group_node_id", -1))
	var node_id := int(params.get("node_id", -1))

	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "shader_path must start with res://.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	var shader: VisualShader = ResourceLoader.load(path)
	if shader == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load shader '%s'." % path)

	var resolved := _resolve_group(shader, int(shader.get_mode()), group_node_id)
	if not resolved["ok"]:
		return _router._fail(str(resolved["error"]), str(resolved["hint"]))
	var group: Resource = resolved["group"]
	if not (node_id in group.call("get_node_list")):
		return _router._fail("RESOURCE_NOT_FOUND", "No node with id %d in group." % node_id)
	var node: VisualShaderNode = group.call("get_node", node_id)
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node with id %d in group." % node_id)
	var position: Vector2 = group.call("get_node_position", node_id)
	var connections: Array = _connections_touching(group.call("get_node_connections"), node_id)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove shader group node %s" % node.get_class())
	ur.add_do_method(group, "remove_node", node_id)
	ur.add_undo_method(self, "_restore_group_node", group, node, position, node_id, connections)
	ur.add_do_method(self, "_save_visual_shader", shader, path)
	ur.add_undo_method(self, "_save_visual_shader", shader, path)
	ur.add_do_reference(shader)
	ur.add_undo_reference(node)
	ur.commit_action()

	return _router._ok({"group_node_id": group_node_id, "node_id": node_id, "removed": true})
