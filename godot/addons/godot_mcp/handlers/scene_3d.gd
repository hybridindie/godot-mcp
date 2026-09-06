@tool
class_name MCPScene3DHandlers
extends RefCounted
## Domain handler: scene 3d.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_mesh_instance"] = _cmd_add_mesh_instance
	handlers["cmd_gridmap_set_cell"] = _cmd_gridmap_set_cell
	handlers["cmd_gridmap_get_cell"] = _cmd_gridmap_get_cell
	handlers["cmd_setup_camera"] = _cmd_setup_camera
	handlers["cmd_setup_environment"] = _cmd_setup_environment
	handlers["cmd_setup_lighting"] = _cmd_setup_lighting


# -- handlers ----------------------------------------------------------------

func _cmd_add_mesh_instance(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var mesh_type := str(params.get("mesh_type", "BoxMesh"))
	var inst := _router._instantiate_validated(mesh_type, "Mesh", "mesh")
	if not inst["ok"]:
		return inst
	var mesh: Mesh = inst["obj"]
	_router._apply_props(mesh, params.get("properties", {}))
	var instance := MeshInstance3D.new()
	instance.name = str(params.get("name", "MeshInstance3D"))
	instance.mesh = mesh
	var path := _router._commit_add_child(parent, instance, "Add %s" % instance.name)
	return _router._ok({"node_path": path, "mesh_type": mesh_type, "created": true})



func _cmd_setup_camera(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var camera := Camera3D.new()
	camera.name = str(params.get("name", "Camera3D"))
	_router._apply_props(camera, params.get("properties", {}))
	var make_current := bool(params.get("make_current", true))
	camera.current = make_current
	var path := _router._commit_add_child(parent, camera, "Add %s" % camera.name)
	return _router._ok({"node_path": path, "current": make_current, "created": true})



func _cmd_setup_lighting(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var light_type := str(params.get("light_type", "DirectionalLight3D"))
	var inst := _router._instantiate_validated(light_type, "Light3D", "light")
	if not inst["ok"]:
		return inst
	var light: Light3D = inst["obj"]
	light.name = str(params.get("name", light_type))
	_router._apply_props(light, params.get("properties", {}))
	var path := _router._commit_add_child(parent, light, "Add %s" % light.name)
	return _router._ok({"node_path": path, "light_type": light_type, "created": true})



func _cmd_setup_environment(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var world_env := WorldEnvironment.new()
	world_env.name = str(params.get("name", "WorldEnvironment"))
	var environment := Environment.new()
	_router._apply_props(environment, params.get("properties", {}))
	world_env.environment = environment
	var path := _router._commit_add_child(parent, world_env, "Add %s" % world_env.name)
	return _router._ok({"node_path": path, "created": true})



func _cmd_gridmap_set_cell(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is GridMap):
		return _router._fail("VALIDATION_ERROR", "Node is not a GridMap.")
	var grid_map: GridMap = node
	if grid_map.mesh_library == null:
		return _router._fail("VALIDATION_ERROR", "GridMap has no mesh_library; assign one first.", "mesh_library")
	var raw_pos: Variant = params.get("position")
	if not (raw_pos is Array) or (raw_pos as Array).size() != 3:
		return _router._fail("VALIDATION_ERROR", "'position' must be a [x, y, z] integer array.")
	var position := Vector3i(int(raw_pos[0]), int(raw_pos[1]), int(raw_pos[2]))
	var item := int(params.get("item", -1))
	var orientation := int(params.get("orientation", 0))
	var prev_item := grid_map.get_cell_item(position)
	var prev_orientation := grid_map.get_cell_item_orientation(position)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set GridMap cell %v" % position)
	ur.add_do_method(grid_map, "set_cell_item", position, item, orientation)
	ur.add_undo_method(grid_map, "set_cell_item", position, prev_item, prev_orientation)
	ur.commit_action()
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"position": [position.x, position.y, position.z],
		"item": item,
	})


## Read a GridMap cell — item + orientation (issue #219 G5). Inverts gridmap_set_cell
## and is symmetric with tilemap_get_cell. No mesh_library needed: an unset cell reads
## back as item == GridMap.INVALID_CELL_ITEM (-1) with empty == true.
func _cmd_gridmap_get_cell(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is GridMap):
		return _router._fail("VALIDATION_ERROR", "Node is not a GridMap.")
	var grid_map: GridMap = node
	var raw_pos: Variant = params.get("position")
	if not (raw_pos is Array) or (raw_pos as Array).size() != 3:
		return _router._fail("VALIDATION_ERROR", "'position' must be a [x, y, z] integer array.")
	var position := Vector3i(int(raw_pos[0]), int(raw_pos[1]), int(raw_pos[2]))
	var item := grid_map.get_cell_item(position)
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"position": [position.x, position.y, position.z],
		"item": item,
		"orientation": grid_map.get_cell_item_orientation(position),
		"empty": item == GridMap.INVALID_CELL_ITEM,
	})


