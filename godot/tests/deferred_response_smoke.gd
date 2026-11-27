@tool
extends SceneTree
## Headless behavior test for deferred command responses (#906).
##
## Run via: godot --headless --path godot/ --script res://tests/deferred_response_smoke.gd
## A handler may answer later: it returns the router's deferred marker, and
## MCPBridge sends the response when the router's completion signal fires —
## same id, same {id, ok, result} / {id, ok:false, error, hint} envelope, one
## command_completed with the real exec_ms. Exactly one response per id: a
## second complete() is refused, a never-completed request is failed with
## TIMEOUT by the addon-side timer, and dispose() fails whatever is pending.
## Drives `_handle_text()` with a send-recording peer (no networking).
## Prints DEFERRED_RESPONSE_TEST_OK, quits 0 on success.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")
const Router := preload("res://addons/godot_mcp/command_router.gd")

# Short addon-side timeout so the TIMEOUT path runs in a smoke, not in 115s.
const TEST_TIMEOUT_SEC := 0.1


func _initialize() -> void:
	# A wall-clock wait inside a frame-capped run: --quit-after counts frames, so
	# cap the rate to keep the frame budget well above the timeout under test.
	Engine.max_fps = 120
	_run()


func _run() -> void:
	var failures: Array[String] = []
	var router: MCPCommandRouter = Router.new()
	router.deferred_timeout_sec = TEST_TIMEOUT_SEC
	# Test handlers: one defers and is completed later by the test; one defers
	# and then answers immediately anyway (must not leak a later TIMEOUT).
	router._handlers["cmd_test_deferred"] = func(_params: Dictionary) -> Dictionary:
		return router.defer()
	router._handlers["cmd_test_defer_then_answer"] = func(_params: Dictionary) -> Dictionary:
		router.defer()
		return router._ok({"answered": "now"})
	var bridge: MCPBridge = Bridge.new(router)
	var peer := Recorder.new()
	bridge._peer = peer
	var completions: Array[Dictionary] = []
	bridge.command_completed.connect(
		func(command: String, exec_ms: float, ok: bool, error_code: String) -> void:
			completions.append({"command": command, "exec_ms": exec_ms, "ok": ok, "error": error_code})
	)

	# The marker is the router's own, not a body shape a handler could produce.
	var marker: Dictionary = router.defer()
	_eq(failures, "defer() with no request in flight is refused", bool(marker.get("ok", true)), false)

	# Reference shape: an immediate reply.
	bridge._handle_text(JSON.stringify({"id": "p1", "command": "cmd_ping", "params": {}}))
	var immediate := _parse(peer.sent[0]) if peer.sent.size() == 1 else {}
	peer.sent.clear()
	completions.clear()

	# 1. Deferred: nothing is sent until complete(); then exactly one response.
	bridge._handle_text(JSON.stringify({"id": "d1", "command": "cmd_test_deferred", "params": {}}))
	_eq(failures, "deferred: nothing sent before completion", peer.sent.size(), 0)
	_eq(failures, "deferred: no command_completed before completion", completions.size(), 0)
	_eq(failures, "deferred: request is pending", router.has_pending("d1"), true)
	OS.delay_msec(5)
	var first: bool = router.complete("d1", router._ok({"baked": true}))
	_eq(failures, "complete() accepts the pending id", first, true)
	_eq(failures, "deferred: one response after completion", peer.sent.size(), 1)
	if peer.sent.size() == 1:
		var resp := _parse(peer.sent[0])
		_eq(failures, "deferred: same id", str(resp.get("id", "")), "d1")
		_eq(failures, "deferred: ok", resp.get("ok", false), true)
		_eq(failures, "deferred: result", resp.get("result", {}), {"baked": true})
		_eq(failures, "deferred: same envelope keys as an immediate reply", _sorted_keys(resp), _sorted_keys(immediate))
	_eq(failures, "deferred: one command_completed", completions.size(), 1)
	if completions.size() == 1:
		_eq(failures, "deferred completion command", completions[0]["command"], "cmd_test_deferred")
		_eq(failures, "deferred completion ok", completions[0]["ok"], true)
		if float(completions[0]["exec_ms"]) < 5.0:
			failures.append("deferred exec_ms should span defer→complete (>= 5ms), got %f" % completions[0]["exec_ms"])
	var second: bool = router.complete("d1", router._ok({"baked": "again"}))
	_eq(failures, "a second complete() for the same id is refused", second, false)
	_eq(failures, "still exactly one response for d1", peer.sent.size(), 1)
	peer.sent.clear()
	completions.clear()

	# 2. Deferred then answered at once: one immediate reply, no later TIMEOUT.
	bridge._handle_text(JSON.stringify({"id": "a1", "command": "cmd_test_defer_then_answer", "params": {}}))
	_eq(failures, "defer-then-answer: one immediate reply", peer.sent.size(), 1)
	_eq(failures, "defer-then-answer: nothing pending", router.has_pending("a1"), false)

	# 3. A deferred sub-command inside run_commands cannot answer later (the batch
	# answers now): it is refused in place and leaves nothing pending.
	bridge._handle_text(JSON.stringify({"id": "b1", "command": "cmd_run_commands", "params": {
		"commands": [{"command": "cmd_test_deferred", "params": {}}],
	}}))
	_eq(failures, "batch: nothing pending", router.has_pending("b1"), false)

	# 4. Never completed: the addon-side timer fails it with TIMEOUT, once.
	bridge._handle_text(JSON.stringify({"id": "t1", "command": "cmd_test_deferred", "params": {}}))
	_eq(failures, "timeout: nothing sent yet", peer.sent.size(), 2)
	await _wait(TEST_TIMEOUT_SEC * 4.0)
	_eq(failures, "timeout: exactly one more response", peer.sent.size(), 3)
	if peer.sent.size() == 3:
		var t := _parse(peer.sent[2])
		_eq(failures, "timeout: same id", str(t.get("id", "")), "t1")
		_eq(failures, "timeout: ok false", t.get("ok", true), false)
		_eq(failures, "timeout: TIMEOUT code", str(t.get("error", "")), "TIMEOUT")
		if str(t.get("hint", "")).is_empty():
			failures.append("timeout: response carries no hint")
	_eq(failures, "timeout: complete() after the timeout is refused", router.complete("t1", router._ok({})), false)
	_eq(failures, "timeout: still one response for t1", peer.sent.size(), 3)
	var timeouts := completions.filter(func(c: Dictionary) -> bool: return c["error"] == "TIMEOUT")
	_eq(failures, "timeout: one TIMEOUT command_completed", timeouts.size(), 1)
	peer.sent.clear()
	completions.clear()

	# 5. dispose() fails what is still pending, once; the timer is then a no-op.
	bridge._handle_text(JSON.stringify({"id": "x1", "command": "cmd_test_deferred", "params": {}}))
	bridge.dispose()
	_eq(failures, "dispose: pending request failed", peer.sent.size(), 1)
	if peer.sent.size() == 1:
		var x := _parse(peer.sent[0])
		_eq(failures, "dispose: same id", str(x.get("id", "")), "x1")
		_eq(failures, "dispose: ok false", x.get("ok", true), false)
	_eq(failures, "dispose: nothing pending", router.has_pending("x1"), false)
	await _wait(TEST_TIMEOUT_SEC * 4.0)
	_eq(failures, "dispose: no late TIMEOUT after dispose", peer.sent.size(), 1)

	bridge.free()
	router = null

	if failures.is_empty():
		print("DEFERRED_RESPONSE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("DEFERRED_RESPONSE_TEST_FAIL")
		quit(1)


func _wait(seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		await process_frame


func _parse(text: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(text)
	return parsed as Dictionary if typeof(parsed) == TYPE_DICTIONARY else {}


func _sorted_keys(d: Dictionary) -> Array:
	var keys := d.keys()
	keys.sort()
	return keys


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


class Recorder:
	extends RefCounted
	## Minimal WebSocketPeer stand-in recording send_text payloads.
	var sent: Array[String] = []

	func send_text(text: String) -> void:
		sent.append(text)

	func close() -> void:
		pass
