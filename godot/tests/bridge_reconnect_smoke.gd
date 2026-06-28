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
	var bridge := Bridge.new()
	var expected: Array[float] = [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]
	for i in expected.size():
		bridge._schedule_retry()
		if absf(bridge._retry_remaining - expected[i]) > 0.001:
			failures.append(
				"backoff step %d: remaining=%f expected=%f" % [i, bridge._retry_remaining, expected[i]]
			)

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

	if failures.is_empty():
		print("BRIDGE_RECONNECT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr(f)
		quit(1)
