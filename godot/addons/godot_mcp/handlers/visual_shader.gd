@tool
class_name MCPVisualShaderHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
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
	ur.create_action("Create visual shader")
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

	var instance: Object = ClassDB.instantiate(node_type)
	if not (instance is VisualShaderNode):
		if not (instance is RefCounted):
			instance.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a VisualShaderNode." % node_type)
	var node: VisualShaderNode = instance

	var mode: int = int(shader.get_mode())
	if shader.has_node(mode, node_id):
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
	if not shader.has_node(mode, node_id):
		return _router._fail("VALIDATION_ERROR", "No node with id %d in shader." % node_id)
	var node: VisualShaderNode = shader.get_node(mode, node_id)

	var prop_type := _router._property_type(node, property)
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
