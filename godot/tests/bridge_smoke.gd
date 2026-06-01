@tool
extends SceneTree
## Headless behavior test for the addon command router (issue #3).
##
## Run via: godot --headless --path godot/ --script res://tests/bridge_smoke.gd
## Exercises MCPCommandRouter.handle() — envelope dispatch and structured errors
## — without any networking, so the command contract is verified deterministically.
## The transport (TCPServer/WebSocketPeer) is covered by the cross-process e2e
## test tests/integration/test_bridge_e2e.py.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	# ping → ok with {pong: true}, echoing the request id.
	var pong: Dictionary = router.handle({"id": "1", "command": "cmd_ping", "params": {}})
	if pong.get("id") != "1":
		failures.append("ping id not echoed: %s" % str(pong.get("id")))
	if pong.get("ok") != true:
		failures.append("ping not ok: %s" % str(pong))
	var result: Variant = pong.get("result")
	if not (result is Dictionary and result.get("pong") == true):
		failures.append("ping result missing pong: %s" % str(result))

	# Unknown command → structured VALIDATION_ERROR, never a crash.
	var unknown: Dictionary = router.handle({"id": "2", "command": "nope"})
	if unknown.get("ok") != false:
		failures.append("unknown command should fail")
	if unknown.get("error") != "VALIDATION_ERROR":
		failures.append("unknown error code: %s" % str(unknown.get("error")))
	if not (unknown.get("hint", "") as String).length() > 0:
		failures.append("unknown command missing hint")

	# Malformed envelope (no command) → structured error, never a crash.
	var malformed: Dictionary = router.handle({"id": "3"})
	if malformed.get("ok") != false:
		failures.append("malformed envelope should fail")
	if malformed.get("error") != "VALIDATION_ERROR":
		failures.append("malformed error code: %s" % str(malformed.get("error")))

	# Non-object params (untrusted JSON) → structured error, never a runtime crash.
	var bad_params: Dictionary = router.handle({"id": "4", "command": "cmd_ping", "params": "oops"})
	if bad_params.get("ok") != false:
		failures.append("non-object params should fail")
	if bad_params.get("error") != "VALIDATION_ERROR":
		failures.append("bad params error code: %s" % str(bad_params.get("error")))

	router = null

	if failures.is_empty():
		print("BRIDGE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("BRIDGE_TEST_FAIL")
		quit(1)
