@tool
class_name MCPPhysicsHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: physics.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_raycast"] = _cmd_add_raycast
	handlers["cmd_set_physics_layers"] = _cmd_set_physics_layers
	handlers["cmd_setup_collision"] = _cmd_setup_collision
	handlers["cmd_setup_physics_body"] = _cmd_setup_physics_body


# -- handlers ----------------------------------------------------------------

func _cmd_setup_physics_body(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is CollisionObject2D or node is CollisionObject3D):
		return _router._fail("VALIDATION_ERROR", "Node is not a physics body/area (CollisionObject2D/3D).")
	var properties: Dictionary = params.get("properties", {})
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Configure body %s" % node.name)
	for key in properties:
		var prop_type := _router._property_type(node, str(key))
		if prop_type == -1:
			continue
		ur.add_do_property(node, str(key), Coerce.from_json(properties[key], prop_type))
		ur.add_undo_property(node, str(key), node.get(str(key)))
	ur.commit_action()
	var applied: Dictionary = {}
	for key in properties:
		if _router._property_type(node, str(key)) != -1:
			applied[str(key)] = Coerce.to_json(node.get(str(key)))
	return _router._ok({"node_path": str(params.get("node_path")), "properties": applied})



func _cmd_setup_collision(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	if not (parent is CollisionObject2D or parent is CollisionObject3D):
		return _router._fail("VALIDATION_ERROR", "Target is not a physics body/area (CollisionObject2D/3D).")
	var root := EditorInterface.get_edited_scene_root()
	var collision_node_type := str(params.get("collision_node_type", "CollisionShape2D"))
	var shape_type := str(params.get("shape_type", ""))
	if not ClassDB.can_instantiate(collision_node_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % collision_node_type)
	if not ClassDB.can_instantiate(shape_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate shape '%s'." % shape_type)

	var shape_obj: Object = ClassDB.instantiate(shape_type)
	if not (shape_obj is Shape2D or shape_obj is Shape3D):
		if not (shape_obj is RefCounted):
			shape_obj.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a Shape2D/Shape3D." % shape_type)
	var shape: Resource = shape_obj
	var shape_props: Dictionary = params.get("properties", {})
	for key in shape_props:
		var pt := _router._property_type(shape, str(key))
		if pt != -1:
			shape.set(str(key), Coerce.from_json(shape_props[key], pt))

	var collision: Node = ClassDB.instantiate(collision_node_type)
	if not (collision is CollisionShape2D or collision is CollisionShape3D):
		collision.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a CollisionShape2D/3D." % collision_node_type)
	collision.name = str(params.get("name", collision_node_type))
	collision.set("shape", shape)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add collision shape to %s" % parent.name)
	ur.add_do_method(parent, "add_child", collision)
	ur.add_do_method(collision, "set_owner", root)
	ur.add_do_reference(collision)
	ur.add_undo_method(parent, "remove_child", collision)
	ur.commit_action()
	return _router._ok({
		"node_path": Inspect.relative_path(collision, root),
		"shape_type": shape_type,
		"created": true,
	})



func _cmd_set_physics_layers(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is CollisionObject2D or node is CollisionObject3D):
		return _router._fail("VALIDATION_ERROR", "Node is not a physics body/area (CollisionObject2D/3D).")
	if params.get("layers") != null and not _router._valid_bits(params["layers"]):
		return _router._fail("VALIDATION_ERROR", "'layers' must be an array of bit indices in [1, 32].")
	if params.get("mask") != null and not _router._valid_bits(params["mask"]):
		return _router._fail("VALIDATION_ERROR", "'mask' must be an array of bit indices in [1, 32].")
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set physics layers on %s" % node.name)
	if params.get("layers") != null:
		ur.add_do_property(node, "collision_layer", _router._bitmask(params["layers"]))
		ur.add_undo_property(node, "collision_layer", node.collision_layer)
	if params.get("mask") != null:
		ur.add_do_property(node, "collision_mask", _router._bitmask(params["mask"]))
		ur.add_undo_property(node, "collision_mask", node.collision_mask)
	ur.commit_action()
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"collision_layer": node.collision_layer,
		"collision_mask": node.collision_mask,
	})



func _cmd_add_raycast(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var raycast_type := str(params.get("raycast_type", "RayCast2D"))
	if not ClassDB.can_instantiate(raycast_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % raycast_type)

	var ray: Node = ClassDB.instantiate(raycast_type)
	if not (ray is RayCast2D or ray is RayCast3D):
		ray.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a RayCast2D/RayCast3D." % raycast_type)
	ray.name = str(params.get("name", raycast_type))
	var ray_props: Dictionary = params.get("properties", {})
	for key in ray_props:
		var pt := _router._property_type(ray, str(key))
		if pt != -1:
			ray.set(str(key), Coerce.from_json(ray_props[key], pt))

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s" % ray.name)
	ur.add_do_method(parent, "add_child", ray)
	ur.add_do_method(ray, "set_owner", root)
	ur.add_do_reference(ray)
	ur.add_undo_method(parent, "remove_child", ray)
	ur.commit_action()
	return _router._ok({"node_path": Inspect.relative_path(ray, root), "created": true})


