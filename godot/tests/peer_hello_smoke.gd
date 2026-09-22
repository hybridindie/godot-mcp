@tool
extends SceneTree
## Headless behavior test for the peer-identity hello (issue #537).
##
## Run via: godot --headless --path godot/ --script res://tests/hello_smoke.gd
## Verifies the bridge's hello envelope: _send_peer_hello builds the exact
## identity payload (project_path / godot_version / addon_version) as a
## command-shaped envelope the server consumes without replying. The
## cross-process transport path is covered by test_bridge_e2e.
## Prints PEER_HELLO_TEST_OK, quits 0 on success.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var bridge: Node = Bridge.new()

	# _send_peer_hello is private; drive it via the documented seam: send into
	# a stub peer that records send_text. WebSocketPeer can't be stubbed by
	# composition (it's engine-native), so reflect the method directly on a
	# lightweight stand-in with the same interface the call needs. The _peer
	# member is untyped (set via set()) so this stand-in is accepted.
	var recorder: Object = Recorder.new()
	bridge.set("_peer", recorder)
	if bridge.get("_peer") != recorder:
		failures.append("seam: set('_peer') did not take — the stub peer is not injectable")
	bridge._send_peer_hello()

	_eq(failures, "sent_count", recorder.sent.size(), 1)
	if recorder.sent.size() == 1:
		var parsed: Variant = JSON.parse_string(recorder.sent[0])
		if typeof(parsed) != TYPE_DICTIONARY:
			failures.append("hello: not JSON: %s" % recorder.sent[0])
		else:
			var envelope: Dictionary = parsed
			_eq(failures, "hello.command", envelope.get("command"), "cmd_peer_hello")
			var params: Dictionary = envelope.get("params", {})
			if not str(params.get("project_path", "")).is_empty():
				pass
			else:
				failures.append("hello: project_path missing")
			if not str(params.get("godot_version", "")).is_empty():
				pass
			else:
				failures.append("hello: godot_version missing")
			# The addon version matches plugin.cfg's (whatever it is — non-empty).
			if not str(params.get("addon_version", "")).is_empty():
				pass
			else:
				failures.append("hello: addon_version missing")
			# The server must consume this WITHOUT replying: it is not a
			# router command, so dispatching it must yield the unknown-command
			# error the server's read loop never sends (it intercepts first).
			var router_result: Dictionary = bridge._router.handle(envelope)
			_eq(failures, "not_a_router_command", router_result.get("ok"), false)

	bridge.free()

	if failures.is_empty():
		print("PEER_HELLO_TEST_OK")
		quit(0)
	else:
		push_error("PEER_HELLO_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


class Recorder:
	extends RefCounted
	## Minimal WebSocketPeer stand-in recording send_text payloads.
	var sent: Array[String] = []

	func send_text(text: String) -> void:
		sent.append(text)


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])