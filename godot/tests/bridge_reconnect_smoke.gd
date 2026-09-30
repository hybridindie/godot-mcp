@tool
extends SceneTree
## Headless deterministic test for the addon bridge's reconnect/backoff state machine
## (#276). No sockets: it drives `_schedule_retry()` and `_process()` directly and asserts
## the backoff doubling+cap and that the retry countdown re-attempts a connection — the
## reconnect logic the live e2e exercises, pinned deterministically without a server.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	# 1. Backoff doubles from _RETRY_MIN (0.5) and caps at _RETRY_MAX (5.0). After each
	#    _schedule_retry() the scheduled `_retry_remaining` follows: 0.5,1,2,4,5,5.
	#    #593: each retry also emits one dock event (attempt N + the delay).
	var bridge := Bridge.new()
	# A retry only happens for an active (started) bridge — #593 gates the retry
	# log on _active so a stop() mid-countdown can't log a reconnect.
	bridge._active = true
	var events: Array[String] = []
	bridge.event_logged.connect(func(message: String) -> void: events.append(message))
	var expected: Array[float] = [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]
	for i in expected.size():
		bridge._schedule_retry()
		if absf(bridge._retry_remaining - expected[i]) > 0.001:
			failures.append(
				"backoff step %d: remaining=%f expected=%f" % [i, bridge._retry_remaining, expected[i]]
			)
	# #593: one event per attempt, naming the attempt number and delay.
	if events.size() != expected.size():
		failures.append("retry events: expected %d, got %d" % [expected.size(), events.size()])
	elif not events[0].contains("attempt 1") or not events[0].contains("0.5s"):
		failures.append("retry event 0: expected 'attempt 1 ... 0.5s', got %s" % events[0])
	elif not events[5].contains("attempt 6"):
		failures.append("retry event 5: expected 'attempt 6', got %s" % events[5])

	# 1b. #593: a stopped bridge never logs a reconnect (stop() sets _active =
	#     false; a stray retry must stay silent while the backoff still advances).
	var b_stopped := Bridge.new()
	var stopped_events: Array[String] = []
	b_stopped.event_logged.connect(func(message: String) -> void: stopped_events.append(message))
	b_stopped._active = false
	b_stopped._schedule_retry()
	if not stopped_events.is_empty():
		failures.append("inactive bridge logged a reconnect: %s" % str(stopped_events))
	if b_stopped._retry_remaining != 0.5:
		failures.append("inactive retry should still advance the backoff, got %f" % b_stopped._retry_remaining)

	# 2. While disconnected, _process counts the backoff down and re-attempts a connection
	#    when it reaches zero (points at a dead port so no real server is touched).
	var b2 := Bridge.new()
	b2._url = "ws://127.0.0.1:1"
	b2._active = true
	b2._peer = null
	b2._retry_remaining = 1.0
	b2._process(0.4)
	if b2._peer != null:
		failures.append("reconnect fired before the backoff elapsed")
	b2._process(0.4)
	b2._process(0.4)  # cumulative 1.2 > 1.0 -> _open() re-attempts the connection
	if b2._peer == null:
		failures.append("retry countdown did not re-attempt a connection")
	b2.stop()

	# 3. #593: a replaced peer holds the REPLACED status and stops reconnecting —
	#    no fight for the bridge after another editor takes it over.
	var b3 := Bridge.new()
	b3._active = true
	b3._peer = _NullPeer.new()
	b3._handle_text(JSON.stringify({
		"id": "peer_replaced", "ok": false, "error": "PEER_REPLACED", "hint": "taken over",
	}))
	if b3.get_status() != Bridge.Status.REPLACED:
		failures.append("replaced: expected REPLACED, got %d" % int(b3.get_status()))
	if b3._active:
		failures.append("replaced: must stop the reconnect loop")

	if failures.is_empty():
		print("BRIDGE_RECONNECT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr(f)
		quit(1)


class _NullPeer:
	extends RefCounted
	## Minimal WebSocketPeer stand-in for the notice path (#593) — close() only.
	func close() -> void:
		pass
