@tool
class_name MCPNavigationHandlers
extends RefCounted
## Domain handler: navigation.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_bake_navigation_mesh"] = _cmd_bake_navigation_mesh
	handlers["cmd_set_navigation_layers"] = _cmd_set_navigation_layers
	handlers["cmd_setup_navigation_agent"] = _cmd_setup_navigation_agent
	handlers["cmd_setup_navigation_region"] = _cmd_setup_navigation_region


# -- handlers ----------------------------------------------------------------

func _cmd_setup_navigation_region(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var region_type := str(params.get("region_type", "NavigationRegion2D"))
	if region_type != "NavigationRegion2D" and region_type != "NavigationRegion3D":
		return _router._fail("VALIDATION_ERROR", "region_type must be NavigationRegion2D or NavigationRegion3D.")
	var region := ClassDB.instantiate(region_type) as Node
	if region == null:
		return _router._fail("VALIDATION_ERROR", "Could not instantiate '%s'." % region_type)
	region.name = str(params.get("name", region_type))
	# Assign an empty navmesh resource so the region is ready to bake.
	if region is NavigationRegion2D:
		region.navigation_polygon = NavigationPolygon.new()
	else:
		region.navigation_mesh = NavigationMesh.new()
	_router._apply_props(region, params.get("properties", {}))
	var path := _router._commit_add_child(parent, region, "Add %s" % region.name)
	return _router._ok({"node_path": path, "region_type": region_type, "created": true})



func _cmd_setup_navigation_agent(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var agent_type := str(params.get("agent_type", "NavigationAgent2D"))
	if agent_type != "NavigationAgent2D" and agent_type != "NavigationAgent3D":
		return _router._fail("VALIDATION_ERROR", "agent_type must be NavigationAgent2D or NavigationAgent3D.")
	var agent := ClassDB.instantiate(agent_type) as Node
	if agent == null:
		return _router._fail("VALIDATION_ERROR", "Could not instantiate '%s'." % agent_type)
	agent.name = str(params.get("name", agent_type))
	_router._apply_props(agent, params.get("properties", {}))
	var path := _router._commit_add_child(parent, agent, "Add %s" % agent.name)
	return _router._ok({"node_path": path, "agent_type": agent_type, "created": true})



func _cmd_bake_navigation_mesh(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var region: Node = found["node"]
	var ur := EditorInterface.get_editor_undo_redo()
	# Baking mutates the assigned navmesh resource in place. To stay undoable we bake a
	# fresh duplicate (the do/redo target) and keep the original pristine as the undo
	# value, so the snapshot is never the bake target and repeated undo/redo is stable.
	if region is NavigationRegion2D:
		if region.navigation_polygon == null:
			return _router._fail("VALIDATION_ERROR", "Region has no navigation_polygon; assign one first.", "navigation_polygon")
		var original: NavigationPolygon = region.navigation_polygon
		var working: NavigationPolygon = original.duplicate(true)
		ur.create_action("Bake navigation polygon")
		ur.add_do_property(region, "navigation_polygon", working)
		ur.add_do_method(region, "bake_navigation_polygon", false)
		ur.add_do_reference(working)
		ur.add_undo_property(region, "navigation_polygon", original)
		ur.add_undo_reference(original)
		ur.commit_action()
	elif region is NavigationRegion3D:
		if region.navigation_mesh == null:
			return _router._fail("VALIDATION_ERROR", "Region has no navigation_mesh; assign one first.", "navigation_mesh")
		var original: NavigationMesh = region.navigation_mesh
		var working: NavigationMesh = original.duplicate(true)
		ur.create_action("Bake navigation mesh")
		ur.add_do_property(region, "navigation_mesh", working)
		ur.add_do_method(region, "bake_navigation_mesh", false)
		ur.add_do_reference(working)
		ur.add_undo_property(region, "navigation_mesh", original)
		ur.add_undo_reference(original)
		ur.commit_action()
	else:
		return _router._fail("VALIDATION_ERROR", "Node is not a NavigationRegion2D/NavigationRegion3D.")
	return _router._ok({"node_path": str(params.get("node_path")), "baked": true})



func _cmd_set_navigation_layers(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if _router._property_type(node, "navigation_layers") == -1:
		return _router._fail("VALIDATION_ERROR", "Node has no 'navigation_layers' property.")
	if not _valid_bits(params.get("layers")):
		return _router._fail("VALIDATION_ERROR", "'layers' must be an array of bit indices in [1, 32].")
	var mask := _bitmask(params["layers"])
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set navigation layers on %s" % node.name)
	ur.add_do_property(node, "navigation_layers", mask)
	ur.add_undo_property(node, "navigation_layers", node.navigation_layers)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "navigation_layers": mask})


