@tool
extends SceneTree
## Headless behavior test for the bridge auth handshake (issue #538).
##
## Run via: godot --headless --path godot/ --script res://tests/auth_smoke.gd
## Verifies the addon's auth envelope: with a token configured the bridge sends
## {command: cmd_auth, params: {token}} as its FIRST message after connecting;
## without one it sends nothing. The token itself never appears in logs. The
## cross-process refusal path is covered by the server-side contract tests and
## the e2e. Prints AUTH_TEST_OK, quits 0 on success.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var bridge: Node = Bridge.new()
	var recorder: Object = Recorder.new()
	bridge.set("_peer", recorder)

	# No token configured: nothing is sent (zero-config path stays byte-identical).
	# start() is NOT called (it opens a real WebSocketPeer); the token-resolution
	# seam (_auth_token) is set directly, mirroring what start() stores.
	bridge.set("_auth_token", "")
	bridge._send_auth()
	_eq(failures, "no_token_no_send", recorder.sent.size(), 0)

	# Token configured: the auth envelope is sent exactly once, first.
	bridge.set("_auth_token", "test-token-value")
	_eq(failures, "token_set", str(bridge.get("_auth_token")), "test-token-value")
	bridge._send_auth()
	_eq(failures, "auth_sent_count", recorder.sent.size(), 1)
	if recorder.sent.size() == 1:
		var parsed: Variant = JSON.parse_string(recorder.sent[0])
		if typeof(parsed) != TYPE_DICTIONARY:
			failures.append("auth: not JSON: %s" % recorder.sent[0])
		else:
			var envelope: Dictionary = parsed
			_eq(failures, "auth.command", envelope.get("command"), "cmd_auth")
			_eq(failures, "auth.params.token", str(envelope.get("params", {}).get("token", "")), "test-token-value")

	# The server's refusal envelope (ok-shaped, no command) must NOT be echoed
	# back as a response, and must be consumed with a hint log — the recorder
	# stays at the same sent-count after handling it.
	bridge._handle_text(JSON.stringify({
		"id": "auth", "ok": false, "error": "VALIDATION_ERROR",
		"hint": "Bridge auth failed: token mismatch.",
	}))
	_eq(failures, "refusal_not_echoed", recorder.sent.size(), 1)

	# A malformed message still behaves as before (echoes the error envelope).
	bridge._handle_text("not json")
	_eq(failures, "malformed_still_echoed", recorder.sent.size(), 2)

	bridge.free()

	if failures.is_empty():
		print("AUTH_TEST_OK")
		quit(0)
	else:
		push_error("AUTH_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


class Recorder:
	extends RefCounted
	## Minimal WebSocketPeer stand-in recording send_text payloads.
	var sent: Array[String] = []

	func send_text(text: String) -> void:
		sent.append(text)

	func close() -> void:
		pass


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])