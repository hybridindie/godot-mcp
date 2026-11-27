@tool
class_name MCPNavigationHandlers
extends RefCounted
## Domain handler: navigation.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter
# Bakes in flight, keyed by region instance id (#906): one bake per region and
# per source resource. Entry: {id, region: WeakRef, resources: [instance ids of
# the original and its working copy], callable: the bake_finished connection}.
var _baking: Dictionary = {}
## Test seam: the persistence verdict for a baked region (headless -s has no
## edited scene to judge it against). Production leaves it unset.
var persistence_probe: Callable = Callable()


func _init(router: MCPCommandRouter) -> void:
	_router = router
	# A bake's request can be answered without bake_finished (TIMEOUT, a dropped
	# session, dispose) — e.g. the region was freed mid-bake, so the signal never
	# fires. Drop the lock then, or the region would refuse every later bake.
	_router.deferred_completed.connect(_on_request_answered)


func register(handlers: Dictionary) -> void:
	handlers["cmd_bake_navigation_mesh"] = _cmd_bake_navigation_mesh
	handlers["cmd_get_navigation_region"] = _cmd_get_navigation_region
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
	# The whitelist above already bounds the type; the helper still guards the null case.
	var region_inst := _router._instantiate_validated(region_type, "", "")
	if not region_inst["ok"]:
		return region_inst
	var region: Node = region_inst["obj"]
	region.name = str(params.get("name", region_type))
	# Assign an empty navmesh resource so the region is ready to bake.
	if region is NavigationRegion2D:
		region.navigation_polygon = NavigationPolygon.new()
	else:
		region.navigation_mesh = NavigationMesh.new()
	_router._helpers.apply_props(region, params.get("properties", {}))
	# #477 (parent rule): a nav region under an instanced child is lost on save.
	var committed := _router._helpers.commit_add_child_with_persistence(parent, region, "Add %s" % region.name)
	return _router._ok(_router._helpers.with_persistence({
		"node_path": committed["path"],
		"region_type": region_type,
		"created": true,
	}, committed["persistence"]))



func _cmd_setup_navigation_agent(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var agent_type := str(params.get("agent_type", "NavigationAgent2D"))
	if agent_type != "NavigationAgent2D" and agent_type != "NavigationAgent3D":
		return _router._fail("VALIDATION_ERROR", "agent_type must be NavigationAgent2D or NavigationAgent3D.")
	# The whitelist above already bounds the type; the helper still guards the null case.
	var agent_inst := _router._instantiate_validated(agent_type, "", "")
	if not agent_inst["ok"]:
		return agent_inst
	var agent: Node = agent_inst["obj"]
	agent.name = str(params.get("name", agent_type))
	_router._helpers.apply_props(agent, params.get("properties", {}))
	# #477 (parent rule): a nav agent under an instanced child is lost on save.
	var committed := _router._helpers.commit_add_child_with_persistence(parent, agent, "Add %s" % agent.name)
	return _router._ok(_router._helpers.with_persistence({
		"node_path": committed["path"],
		"agent_type": agent_type,
		"created": true,
	}, committed["persistence"]))



func _cmd_bake_navigation_mesh(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	return start_bake(found["node"], str(params.get("node_path")))


## Start a threaded bake of `region` and answer the current request when it
## finishes (#906). Returns the router's deferred marker, or a structured failure
## (bad region, a bake already running on it, or defer() refused — no request
## id, inside run_commands) without starting anything.
##
## The bake runs on a fresh duplicate of the region's resource, so the original
## stays pristine as the undo value: the UndoRedo action is registered when the
## bake lands, and undo puts the previous resource back.
func start_bake(region: Node, node_path: String) -> Dictionary:
	var prop := ""
	if region is NavigationRegion2D:
		prop = "navigation_polygon"
	elif region is NavigationRegion3D:
		prop = "navigation_mesh"
	else:
		return _router._fail("VALIDATION_ERROR", "Node is not a NavigationRegion2D/NavigationRegion3D.")
	var original: Resource = region.get(prop)
	if original == null:
		return _router._fail("VALIDATION_ERROR", "Region has no %s; assign one first." % prop, prop)
	# godot-async rule: one in-flight operation per target. The engine refuses a
	# second bake of the same resource too, but only with a push_error.
	_prune_stale()
	var key := region.get_instance_id()
	# is_baking goes through call(): it is bound on both region classes from the
	# 4.4 floor up (verified in 4.4-stable), but on an engine without it call()
	# errors and returns null, and this guard degrades to MCP-started bakes only —
	# a bake the user started from the viewport would not be refused here.
	if _baking.has(key) or bool(region.call("is_baking")):
		return _router._fail(
			"EDITOR_BUSY",
			"A navigation bake is already running on '%s'; wait for its response, then retry." % node_path,
			"node_path",
		)
	# Regions can share one resource: a second bake of a mesh already in flight
	# would bake the first bake's undo value in place.
	var source_id := original.get_instance_id()
	for entry: Dictionary in _baking.values():
		if (entry.get("resources", []) as Array).has(source_id):
			return _router._fail(
				"EDITOR_BUSY",
				"The %s on '%s' is shared with a region whose bake is still running; wait for that response, then retry." % [prop, node_path],
				"node_path",
			)
	var marker := _router.defer()
	if not _router.is_deferred(marker):
		return marker
	var id := str(marker.get("id", ""))
	var working: Resource = original.duplicate(true)
	region.set(prop, working)
	var on_finished := _on_bake_finished.bind(region, id, node_path, prop, original, working)
	_baking[key] = {
		"id": id,
		"region": weakref(region),
		"resources": [source_id, working.get_instance_id()],
		"callable": on_finished,
	}
	# bake_finished can fire synchronously (the bake fails before it reaches the
	# thread, e.g. an empty 2D region); the router then answers inside this call
	# and drops the marker. bake_finished is emitted on the main thread (the
	# engine call_deferreds its _bake_finished off the bake thread), which is
	# what complete() requires.
	if region is NavigationRegion2D:
		var region_2d := region as NavigationRegion2D
		region_2d.bake_finished.connect(on_finished, CONNECT_ONE_SHOT)
		region_2d.bake_navigation_polygon(true)
	else:
		var region_3d := region as NavigationRegion3D
		region_3d.bake_finished.connect(on_finished, CONNECT_ONE_SHOT)
		region_3d.bake_navigation_mesh(true)
	return marker


func _on_bake_finished(region: Node, id: String, node_path: String, prop: String, original: Resource, working: Resource) -> void:
	var key := region.get_instance_id()
	if str((_baking.get(key, {}) as Dictionary).get("id", "")) == id:
		_baking.erase(key)
	if region.get(prop) != working:
		# The editor stays responsive during a threaded bake, so the property can
		# be replaced mid-bake (its own undo step). The baked copy is orphaned:
		# keep the user's resource and history, and say nothing was baked.
		_router.complete(id, _router._ok({
			"node_path": node_path,
			"baked": false,
			"hint": "The region's %s changed while the bake ran; the baked result was discarded and the new %s kept. Re-run the bake." % [prop, prop],
		}))
		return
	var polygon_count := -1
	var vertex_count := -1
	if working is NavigationPolygon:
		var poly := working as NavigationPolygon
		polygon_count = poly.get_polygon_count()
		# NavigationPolygon has no get_vertex_count(); count the vertex array.
		vertex_count = poly.get_vertices().size()
	elif working is NavigationMesh:
		var mesh := working as NavigationMesh
		polygon_count = mesh.get_polygon_count()
		# Guarded like _cmd_get_navigation_region: an error here would skip the
		# undo registration and leave the request to the TIMEOUT.
		vertex_count = mesh.get_vertices().size() if mesh.has_method("get_vertices") else 0
	# A bake that produced zero polygons is a failed bake (no source geometry was
	# parsed, or every agent/geometry filter excluded it) — never report baked:true
	# for an empty navmesh, an agent trusting that ships AI that can't pathfind (#413).
	# Nothing useful landed, so put the previous resource back instead of an undo step.
	if polygon_count <= 0:
		region.set(prop, original)
		_router.complete(id, _router._fail(
			"VALIDATION_ERROR",
			("Bake produced no polygons (%d vertices) — no source geometry was parsed. Add "
				+ "MeshInstance3D/GridMap/StaticBody colliders under the region (or under "
				+ "the root_node_type the mesh parses) and retry.") % vertex_count,
			"polygon_count",
		))
		return
	# Registered even when complete() is refused (the request timed out or the
	# plugin shut down): the bake still landed, so it must stay undoable.
	# The bake already applied the do value, so commit without executing.
	var ur: Variant = _undo_redo()
	ur.create_action("Bake navigation polygon" if prop == "navigation_polygon" else "Bake navigation mesh")
	ur.add_do_property(region, prop, working)
	ur.add_do_reference(working)
	ur.add_undo_property(region, prop, original)
	ur.add_undo_reference(original)
	ur.commit_action(false)
	# The bake assigns a fresh duplicate to the region, so it saves like any node property.
	_router.complete(id, _router._ok(_router._helpers.with_persistence({
		"node_path": node_path,
		"baked": true,
		"polygon_count": polygon_count,
		"vertex_count": vertex_count,
	}, _persistence(region))))


# A request was answered (#906). If it was a bake that bake_finished did not
# answer (TIMEOUT, dropped session, dispose), drop its lock unless the region is
# still genuinely baking — then bake_finished will drop it.
func _on_request_answered(_command: String, response: Dictionary, _exec_ms: float) -> void:
	var id := str(response.get("id", ""))
	for key: int in _baking.keys():
		var entry: Dictionary = _baking[key]
		if str(entry.get("id", "")) == id and _is_stale(entry):
			_release_lock(key)


# Drop locks whose request is gone and whose region is freed or idle (belt and
# braces for a lock _on_request_answered could not clear).
func _prune_stale() -> void:
	for key: int in _baking.keys():
		var entry: Dictionary = _baking[key]
		if not _router.has_pending(str(entry.get("id", ""))) and _is_stale(entry):
			_release_lock(key)


func _is_stale(entry: Dictionary) -> bool:
	var region: Node = (entry.get("region") as WeakRef).get_ref() if entry.get("region") is WeakRef else null
	return region == null or not bool(region.call("is_baking"))


# Release a lock and its bake_finished connection: a connection left behind
# would also fire on the region's next bake and answer for the wrong request.
func _release_lock(key: int) -> void:
	var entry: Dictionary = _baking[key]
	_baking.erase(key)
	var region: Node = (entry.get("region") as WeakRef).get_ref() if entry.get("region") is WeakRef else null
	var on_finished: Callable = entry.get("callable", Callable())
	if region != null and on_finished.is_valid() and region.is_connected("bake_finished", on_finished):
		region.disconnect("bake_finished", on_finished)


# The editor's undo manager, or the router's history seam in headless tests
# (no EditorUndoRedoManager there). Variant because the two types share the
# action API but not a base class.
func _undo_redo() -> Variant:
	if _router._history_override != null:
		return _router._history_override
	return EditorInterface.get_editor_undo_redo()


func _persistence(region: Node) -> Dictionary:
	if persistence_probe.is_valid():
		return persistence_probe.call(region)
	return _router._helpers.persistent_target(region)



func _cmd_get_navigation_region(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var region: Node = found["node"]
	var path := str(params.get("node_path"))
	if region is NavigationRegion2D:
		var navpoly: NavigationPolygon = region.navigation_polygon
		if navpoly == null:
			return _router._ok({
				"node_path": path,
				"has_polygon": false,
				"outline_count": 0,
				"vertex_count": 0,
				"polygon_count": 0,
			})
		return _router._ok({
			"node_path": path,
			"has_polygon": true,
			"outline_count": navpoly.get_outline_count(),
			"vertex_count": navpoly.get_vertex_count(),
			"polygon_count": navpoly.get_polygon_count(),
		})
	elif region is NavigationRegion3D:
		var navmesh: NavigationMesh = region.navigation_mesh
		if navmesh == null:
			return _router._ok({
				"node_path": path,
				"has_polygon": false,
				"outline_count": 0,
				"vertex_count": 0,
				"polygon_count": 0,
			})
		var vertex_count := 0
		if navmesh.has_method("get_vertices"):
			var verts: PackedVector3Array = navmesh.get_vertices()
			vertex_count = verts.size()
		return _router._ok({
			"node_path": path,
			"has_polygon": true,
			"outline_count": 0,
			"vertex_count": vertex_count,
			"polygon_count": navmesh.get_polygon_count(),
		})
	return _router._fail("VALIDATION_ERROR", "Node is not a NavigationRegion2D/NavigationRegion3D.")



func _cmd_set_navigation_layers(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if _router._helpers.property_type(node, "navigation_layers") == -1:
		return _router._fail("VALIDATION_ERROR", "Node has no 'navigation_layers' property.")
	if not _router._helpers.valid_bits(params.get("layers")):
		return _router._fail("VALIDATION_ERROR", "'layers' must be an array of bit indices in [1, 32].")
	var mask: int = _router._helpers.bitmask(params["layers"])
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set navigation layers on %s" % node.name)
	ur.add_do_property(node, "navigation_layers", mask)
	ur.add_undo_property(node, "navigation_layers", node.navigation_layers)
	ur.commit_action()
	return _router._ok(_router._helpers.with_persistence({"node_path": str(params.get("node_path")), "navigation_layers": mask}, _router._helpers.persistent_target(node)))


