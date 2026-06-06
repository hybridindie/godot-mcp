@tool
class_name MCPProfilingHandlers
extends RefCounted
## Domain handler: profiling.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

# Curated, JSON-safe Performance monitors (name → Performance.Monitor enum). Shared shape
# with the probe's snapshot so editor and running-game readings line up.
const _PERF_MONITORS := {
	"fps": Performance.TIME_FPS,
	"process_time": Performance.TIME_PROCESS,
	"physics_process_time": Performance.TIME_PHYSICS_PROCESS,
	"memory_static": Performance.MEMORY_STATIC,
	"memory_static_max": Performance.MEMORY_STATIC_MAX,
	"object_count": Performance.OBJECT_COUNT,
	"node_count": Performance.OBJECT_NODE_COUNT,
	"resource_count": Performance.OBJECT_RESOURCE_COUNT,
	"orphan_node_count": Performance.OBJECT_ORPHAN_NODE_COUNT,
	"objects_drawn": Performance.RENDER_TOTAL_OBJECTS_IN_FRAME,
	"primitives_drawn": Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME,
	"draw_calls": Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME,
	"video_mem_used": Performance.RENDER_VIDEO_MEM_USED,
	"texture_mem_used": Performance.RENDER_TEXTURE_MEM_USED,
	"buffer_mem_used": Performance.RENDER_BUFFER_MEM_USED,
	"physics_2d_active": Performance.PHYSICS_2D_ACTIVE_OBJECTS,
	"physics_3d_active": Performance.PHYSICS_3D_ACTIVE_OBJECTS,
}

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_editor_performance"] = _cmd_get_editor_performance
	handlers["cmd_get_performance_monitors"] = _cmd_get_performance_monitors


# -- handlers ----------------------------------------------------------------

func _cmd_get_editor_performance(_params: Dictionary) -> Dictionary:
	var monitors: Dictionary = {}
	for name in _PERF_MONITORS:
		monitors[name] = Performance.get_monitor(_PERF_MONITORS[name])
	return _router._ok({"monitors": monitors})



func _cmd_get_performance_monitors(_params: Dictionary) -> Dictionary:
	if not EditorInterface.is_playing_scene():
		return _router._fail("PRECONDITION_FAILED", "No play session. Run play_scene first.", "play_session")
	if _router._debugger == null or not _router._debugger.is_connected_to_probe():
		return _router._ok({
			"playing": true, "connected": false, "ready": true, "monitors": {},
			"hint": "Add the godot_mcp runtime probe autoload to the game for live monitors.",
		})
	_router._debugger.send_to_probe("godot_mcp:get_performance", [])
	var cached: Variant = _router._debugger.get_performance()
	return _router._ok({
		"playing": true,
		"connected": true,
		"ready": cached != null,
		"monitors": cached if cached != null else {},
	})


