@tool
extends SceneTree
## Headless behavior test for the threaded, deferred navmesh bake (#906).
##
## Run via: godot --headless --path godot/ --script res://tests/deferred_bake_smoke.gd
## cmd_bake_navigation_mesh bakes on a thread and answers through the router's
## deferred response when the region's bake_finished fires: the immediate
## return is the deferred marker (nothing sent), readiness heartbeats keep
## flowing while frames are pumped, exactly one response arrives with the baked
## counts, a second bake of the same region is refused while one runs, a bake
## inside run_commands is refused before it starts, and undo restores the
## region's previous navigation mesh.
##
## Headless -s has no edited scene and no EditorUndoRedoManager, so the smoke
## drives the handler's bake entry on a region it built (a test command in the
## router's table, the deferred_response_smoke pattern) and pins the undo
## history with the router's history seam. The live path is the e2e suite.
## Prints DEFERRED_BAKE_TEST_OK, quits 0 on success.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")
const Router := preload("res://addons/godot_mcp/command_router.gd")

# Frames to wait for a bake before calling it hung (a tiny box bakes in a few).
const MAX_BAKE_FRAMES := 600
# The original mesh's hand-made polygon count, so undo is told apart from a bake.
const ORIGINAL_POLYGONS := 1


func _initialize() -> void:
	Engine.max_fps = 120
	_run()


func _run() -> void:
	# Nodes added in _initialize are not inside the tree yet; geometry parsing needs it.
	await process_frame
	var failures: Array[String] = []
	var router: MCPCommandRouter = Router.new()
	var ur := UndoRedo.new()
	router.set_history_seam(ur)
	var nav: MCPNavigationHandlers = null
	for handler in router._instances:
		if handler is MCPNavigationHandlers:
			nav = handler
	if nav == null:
		_finish(["router has no MCPNavigationHandlers instance"])
		return
	# Headless: no edited scene to judge persistence against.
	nav.persistence_probe = func(_node: Node) -> Dictionary:
		return {"ok": true}

	var region := _build_region()
	var original: NavigationMesh = region.navigation_mesh
	# The node path is resolved against the edited scene in production; here the
	# test command hands the handler the region it built.
	router._handlers["cmd_test_bake"] = func(_params: Dictionary) -> Dictionary:
		return nav.start_bake(region, "Nav")

	var bridge: MCPBridge = TestBridge.new(router)
	var peer := Recorder.new()
	bridge._peer = peer
	bridge._active = true
	var completions: Array[Dictionary] = []
	bridge.command_completed.connect(
		func(command: String, exec_ms: float, ok: bool, error_code: String) -> void:
			completions.append({"command": command, "exec_ms": exec_ms, "ok": ok, "error": error_code})
	)
	# Connect (peer hello + first heartbeat), then start from a clean record.
	bridge._process(0.0)
	peer.sent.clear()

	# 1. The bake defers: no body now, the request is pending, the bake is running.
	bridge._handle_text(JSON.stringify({"id": "b1", "command": "cmd_test_bake", "params": {}}))
	_eq(failures, "bake: nothing sent at once (deferred)", _responses(peer, "b1").size(), 0)
	_eq(failures, "bake: request is pending", router.has_pending("b1"), true)
	_eq(failures, "bake: runs on a thread (region is baking)", region.is_baking(), true)
	var working: NavigationMesh = region.navigation_mesh
	_eq(failures, "bake: the original mesh is not the bake target", working != original, true)

	# 2. A second bake of the same region while one runs is refused at once.
	bridge._handle_text(JSON.stringify({"id": "b2", "command": "cmd_test_bake", "params": {}}))
	var busy := _responses(peer, "b2")
	_eq(failures, "concurrent: one immediate reply", busy.size(), 1)
	if busy.size() == 1:
		_eq(failures, "concurrent: refused", busy[0].get("ok", true), false)
		_eq(failures, "concurrent: EDITOR_BUSY", str(busy[0].get("error", "")), "EDITOR_BUSY")
		if str(busy[0].get("hint", "")).is_empty():
			failures.append("concurrent: refusal carries no hint")
	_eq(failures, "concurrent: not left pending", router.has_pending("b2"), false)

	# 3. Pump frames until the bake answers; heartbeats keep flowing meanwhile.
	# Prime the cadence so the next frame owes a heartbeat (the bake is short).
	bridge._status_timer = 0.99
	var heartbeats_while_pending := 0
	var frames := 0
	while _responses(peer, "b1").is_empty() and frames < MAX_BAKE_FRAMES:
		# The editor's main loop keeps ticking the bridge while the bake runs.
		var pending := router.has_pending("b1")
		var before := _heartbeats(peer)
		bridge._process(0.02)
		if pending:
			heartbeats_while_pending += _heartbeats(peer) - before
		await process_frame
		frames += 1
	if heartbeats_while_pending < 1:
		failures.append("heartbeat: no cmd_editor_status sent while the bake was pending")
	var answers := _responses(peer, "b1")
	_eq(failures, "bake: exactly one response", answers.size(), 1)
	if answers.size() == 1:
		var r: Dictionary = answers[0]
		_eq(failures, "bake: ok", r.get("ok", false), true)
		var result: Dictionary = r.get("result", {})
		_eq(failures, "bake: node_path", str(result.get("node_path", "")), "Nav")
		_eq(failures, "bake: baked", result.get("baked", false), true)
		if int(result.get("polygon_count", 0)) <= 0:
			failures.append("bake: polygon_count should be > 0, got %s" % str(result.get("polygon_count")))
		if int(result.get("vertex_count", 0)) <= 0:
			failures.append("bake: vertex_count should be > 0, got %s" % str(result.get("vertex_count")))
		_eq(failures, "bake: result carries persistence", result.has("persisted"), true)
	var bake_done := completions.filter(func(c: Dictionary) -> bool: return c["command"] == "cmd_test_bake" and c["ok"])
	_eq(failures, "bake: one successful command_completed", bake_done.size(), 1)
	_eq(failures, "bake: nothing pending after completion", router.has_pending("b1"), false)
	_eq(failures, "bake: the region holds the baked mesh", region.navigation_mesh == working, true)
	# No late duplicate (e.g. a stray timer or a second bake_finished).
	for i in 10:
		await process_frame
	_eq(failures, "bake: still exactly one response later", _responses(peer, "b1").size(), 1)

	# 4. Undo restores the previous navigation mesh; redo puts the baked one back.
	var undone: Dictionary = router.handle({"id": "u1", "command": "cmd_undo", "params": {"count": 1}})
	_eq(failures, "undo: ok", undone.get("ok", false), true)
	_eq(failures, "undo: restores the previous mesh", region.navigation_mesh == original, true)
	_eq(failures, "undo: previous mesh untouched by the bake", original.get_polygon_count(), ORIGINAL_POLYGONS)
	router.handle({"id": "r1", "command": "cmd_redo", "params": {"count": 1}})
	_eq(failures, "redo: the baked mesh is back", region.navigation_mesh == working, true)

	# 5. Inside run_commands the bake cannot answer later: refused before it starts.
	var before_batch: NavigationMesh = region.navigation_mesh
	var undo_depth := ur.get_history_count()
	bridge._handle_text(JSON.stringify({"id": "c1", "command": "cmd_run_commands", "params": {
		"commands": [{"command": "cmd_test_bake", "params": {}}],
	}}))
	_eq(failures, "batch: bake never started", region.is_baking(), false)
	_eq(failures, "batch: region mesh untouched", region.navigation_mesh == before_batch, true)
	_eq(failures, "batch: no undo action", ur.get_history_count(), undo_depth)
	_eq(failures, "batch: nothing pending", router.has_pending("c1"), false)
	var batch := _responses(peer, "c1")
	_eq(failures, "batch: exactly one response", batch.size(), 1)
	if batch.size() == 1:
		var results: Array = (batch[0].get("result", {}) as Dictionary).get("results", [])
		if results.size() == 1:
			_eq(failures, "batch: sub-result refused", (results[0] as Dictionary).get("ok", true), false)
		else:
			failures.append("batch: expected one sub-result, got %d" % results.size())

	bridge.dispose()
	bridge.free()
	ur.free()
	region.queue_free()
	_finish(failures)


func _finish(failures: Array[String]) -> void:
	if failures.is_empty():
		print("DEFERRED_BAKE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("DEFERRED_BAKE_TEST_FAIL")
		quit(1)


# A region over a 10x10 static floor, holding a hand-made one-triangle mesh so
# the pre-bake state is recognisable after undo.
func _build_region() -> NavigationRegion3D:
	var region := NavigationRegion3D.new()
	region.name = "Nav"
	var mesh := NavigationMesh.new()
	mesh.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	mesh.vertices = PackedVector3Array([Vector3.ZERO, Vector3(1, 0, 0), Vector3(0, 0, 1)])
	mesh.add_polygon(PackedInt32Array([0, 1, 2]))
	region.navigation_mesh = mesh
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(10, 0.2, 10)
	shape.shape = box
	body.add_child(shape)
	region.add_child(body)
	root.add_child(region)
	return region


func _responses(peer: Recorder, id: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for text in peer.sent:
		var d := _parse(text)
		if str(d.get("id", "")) == id and d.has("ok"):
			out.append(d)
	return out


func _heartbeats(peer: Recorder) -> int:
	var n := 0
	for text in peer.sent:
		if str(_parse(text).get("command", "")) == "cmd_editor_status":
			n += 1
	return n


func _parse(text: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(text)
	return parsed as Dictionary if typeof(parsed) == TYPE_DICTIONARY else {}


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


## Headless -s has no editor filesystem or base control to read readiness from;
## the heartbeat cadence under test is the bridge's own.
class TestBridge:
	extends "res://addons/godot_mcp/mcp_bridge.gd"

	func _detect_editor_status() -> String:
		return "ready"


## Minimal open WebSocketPeer stand-in recording send_text payloads.
class Recorder:
	extends RefCounted
	var sent: Array[String] = []

	func send_text(text: String) -> void:
		sent.append(text)

	func poll() -> void:
		pass

	func get_ready_state() -> int:
		return WebSocketPeer.STATE_OPEN

	func get_available_packet_count() -> int:
		return 0

	func close() -> void:
		pass
